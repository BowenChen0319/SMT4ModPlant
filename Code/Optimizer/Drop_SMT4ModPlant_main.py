import json
from z3 import Solver, Bool, Not, Sum, If, is_true, sat, And

TRANSPORT_CAPABILITIES = ["Dosing", "Transfer", "Discharge"]

def load_json(filename):
    with open(filename, 'r', encoding='utf-8') as f:
        return json.load(f)

def capability_matching(recipe_sem_id, cap_entry):
    cap_id = cap_entry['capability'][0]['capability_ID']
    if cap_id == recipe_sem_id:
        return True
    generalized = cap_entry.get('generalized_by', [])
    if isinstance(generalized, list) and recipe_sem_id.split('#')[-1] in generalized:
        return True
    return False

def property_value_match(param_value, prop):
    import re
    discrete_values = []
    for k, v in prop.items():
        if k.startswith('value') and k != 'valueType' and v is not None:
            try:
                discrete_values.append(float(v))
            except (ValueError, TypeError):
                continue

    value_min = prop.get('valueMin')
    value_max = prop.get('valueMax')

    if value_min is not None or value_max is not None:
        match = re.match(r'(>=|<=|>|<|=)?\s*([0-9\.,]+)', str(param_value))
        if match:
            op, val = match.groups()
            val = float(val.replace(',', '.'))
            op = op or '='
            if value_min is not None:
                try:
                    value_min_f = float(value_min)
                    if op in ('=', '>=') and val < value_min_f:
                        return False
                    if op == '>' and val <= value_min_f:
                        return False
                except ValueError:
                    pass
            if value_max is not None:
                try:
                    value_max_f = float(value_max)
                    if op in ('=', '<=') and val > value_max_f:
                        return False
                    if op == '<' and val >= value_max_f:
                        return False
                except ValueError:
                    pass
            return True

    if discrete_values:
        match = re.match(r'(>=|<=|>|<|=)?\s*([0-9\.,]+)', str(param_value))
        if match:
            op, val = match.groups()
            op = op or '='
            pval = float(val.replace(',', '.'))
            if op in ('=', None):
                return pval in discrete_values
            elif op == '>=':
                return any(dv >= pval for dv in discrete_values)
            elif op == '<=':
                return any(dv <= pval for dv in discrete_values)
            elif op == '>':
                return any(dv > pval for dv in discrete_values)
            elif op == '<':
                return any(dv < pval for dv in discrete_values)
        return False

    return True

def properties_compatible(recipe_step, cap_entry):
    if "Parameters" not in recipe_step or not recipe_step["Parameters"]:
        return True, []
    matched_props = []
    for param in recipe_step["Parameters"]:
        param_key = param.get("Key")
        param_unit = param.get("UnitOfMeasure")
        value_str = param.get("ValueString")
        match_found = False
        for prop in cap_entry.get("properties", []):
            if prop.get("property_ID") == param_key:
                if param_unit and prop.get("property_unit") and param_unit != prop.get("property_unit"):
                    continue
                if property_value_match(value_str, prop):
                    matched_props.append((param, prop))
                    match_found = True
                    break
        if not match_found:
            print(f"[DEBUG-Property-Match] No Property-Match for Parameter: {param['Description']} (Key: {param_key}, Unit: {param_unit}, Value: {value_str}) in Capability '{cap_entry['capability'][0]['capability_name']}'")
            return False, []
        else:
            print(f"[DEBUG-Property-Match] Match for Parameter: {param['Description']} in Capability '{cap_entry['capability'][0]['capability_name']}'")
    return True, matched_props

def check_preconditions_for_step(recipe, step, cap_entry):
    step_id = step['ID']
    input_material_ids = [link['FromID'] for link in recipe['DirectedLinks'] if link['ToID'] == step_id]
    materials = recipe.get('Inputs', []) + recipe.get('Intermediates', [])
    input_materials = [mat for mat in materials if mat['ID'] in input_material_ids]
    for prop in cap_entry.get('properties', []):
        for constraint in prop.get('property_constraint', []):
            if constraint.get('conditional_type') == "Pre":
                constraint_id = constraint.get('property_constraint_ID')
                constraint_unit = constraint.get('property_constraint_unit')
                constraint_value_str = constraint.get('property_constraint_value')
                matched = False
                for mat in input_materials:
                    if mat.get('Key') == constraint_id and mat.get('UnitOfMeasure') == constraint_unit:
                        try:
                            import re
                            match = re.match(r'(>=|<=|>|<|=)?\s*([0-9\.,]+)', constraint_value_str)
                            if match:
                                op, val = match.groups()
                                op = op or '='
                                cval = float(val.replace(',', '.'))
                                mval = float(mat['Quantity'])
                                if (
                                    (op == '>=' and mval >= cval) or
                                    (op == '>' and mval > cval) or
                                    (op == '<=' and mval <= cval) or
                                    (op == '<' and mval < cval) or
                                    (op == '=' and mval == cval)
                                ):
                                    matched = True
                                    break
                        except Exception:
                            continue
                if not matched:
                    print(f"[DEBUG-Precond] Step {step_id} with capability '{cap_entry['capability'][0]['capability_name']}': Precondition {constraint_id} NOT fulfilled.")
                    return False
    return True

# --- MAIN LOGIC ---

recipe = load_json('parsed_recipe_output.json')
capabilities = load_json('parsed_resource_capabilities_output.json')

process_steps = recipe['ProcessElements']
resources = list(capabilities.keys())
step_resource_to_caps_props = [[[] for _ in resources] for _ in process_steps]
Assignment = []
step_by_id = {step['ID']: idx for idx, step in enumerate(process_steps)}
s = Solver()

def has_transfer_capability(res, capabilities):
    for cap in capabilities[res]:
        if cap['capability'][0]['capability_name'] in TRANSPORT_CAPABILITIES:
            return True
    return False

def needs_transfer_to_step(step, j, resources, step_by_id, step_resource_to_caps_props, recipe):
    step_id = step['ID']
    for link in recipe['DirectedLinks']:
        if link['ToID'] == step_id:
            from_id = link['FromID']
            for idx, candidate_step in enumerate(recipe['ProcessElements']):
                if candidate_step['ID'] == from_id:
                    for k, _ in enumerate(resources):
                        if k != j and isinstance(step_resource_to_caps_props[idx][k], tuple):
                            return True
    return False

assignment_varnames = []
assignment_varmap = {}  # Name → Z3-Bool

for i, step in enumerate(process_steps):
    row = []
    sem_id = step['SemanticDescription']
    for j, res in enumerate(resources):
        cap_list = capabilities[res]
        matching_caps = []
        matching_props = []
        for cap_entry in cap_list:
            match, matched_props = properties_compatible(step, cap_entry) if capability_matching(sem_id, cap_entry) else (False, [])
            if match and not check_preconditions_for_step(recipe, step, cap_entry):
                match = False
                matched_props = []
            if match:
                matching_caps.append(cap_entry['capability'][0]['capability_name'])
                matching_props.append((cap_entry['capability'][0]['capability_name'], matched_props))
        varname = f"assign_{step['ID']}_{res.replace(':', '').replace(' ', '_')}"
        var = Bool(varname)
        assignment_varnames.append(varname)
        assignment_varmap[varname] = var
        transfer_needed = needs_transfer_to_step(step, j, resources, step_by_id, step_resource_to_caps_props, recipe)
        transfer_cap = has_transfer_capability(res, capabilities)
        if transfer_needed and not transfer_cap:
            print(f"[DEBUG-Exclusion-Transfer] Excluding assignment: {step['ID']} -> {res} because transfer/dosing capability is missing!")
            s.add(Not(var))
            row.append(None)
            continue
        row.append(var)
        if matching_caps:
            step_resource_to_caps_props[i][j] = (matching_caps, matching_props)
        else:
            print(f"[DEBUG-Exclusion] Excluding assignment: {step['ID']} -> {res} due to invalid capabilities.")
            s.add(Not(var))
    Assignment.append(row)

def export_smt2_annotated(filename, process_steps, resources, Assignment, step_resource_to_caps_props):
    invalid_assignments = set()
    var_names = {}
    with open(filename, "w", encoding="utf-8") as f:
        f.write("; === Annotated SMT2 Model ===\n(set-logic ALL)\n")
        for i, step in enumerate(process_steps):
            for j, res in enumerate(resources):
                var = Assignment[i][j]
                entry = step_resource_to_caps_props[i][j]
                if isinstance(entry, tuple):
                    caps, _ = entry
                    cap_str = ", ".join(caps)
                else:
                    cap_str = "—"
                    invalid_assignments.add((i, j))
                step_id = step["ID"]
                res_name = res.replace(":", "").replace(" ", "_")
                varname = f"assign_{step_id}_{res_name}"
                var_names[(i, j)] = varname
                f.write(f"; {step['Description']} [{step_id}] -> {res}  (Capabilities: {cap_str})\n")
                f.write(f"(declare-fun {varname} () Bool)\n")
        f.write("\n; Excluded assignments due to failed preconditions or property mismatch\n")
        for (i, j) in invalid_assignments:
            if (i, j) in var_names:
                varname = var_names[(i, j)]
                label = f"precond_fail_{process_steps[i]['ID']}_{resources[j].replace(':', '')}"
                f.write(f"(assert (! (not {varname}) :named {label}))\n")
        f.write("\n")
        for i, step in enumerate(process_steps):
            vars_for_step = []
            for j, res in enumerate(resources):
                var = Assignment[i][j]
                if var is not None:
                    varname = var_names[(i, j)]
                    vars_for_step.append(f"(ite {varname} 1 0)")
            if vars_for_step:
                assert_str = f"(= (+ {' '.join(vars_for_step)}) 1)"
                label = f"assign_unique_{step['ID']}"
                f.write(f"; Step: {step['Description']} [{step['ID']}]: Must be mapped to exactly one resource\n")
                f.write(f"(assert (! {assert_str} :named {label}))\n")
            else:
                label = f"assign_unique_{step['ID']}_UNSAT"
                f.write(f"(assert (! false :named {label}))\n")
        f.write("\n(check-sat)\n")

export_smt2_annotated("smt_model_annotated.smt2", process_steps, resources, Assignment, step_resource_to_caps_props)
print("Annotated SMT2 model with comments and :named assertions exported.")

for i, step_vars in enumerate(Assignment):
    vars_for_step = [v for v in step_vars if v is not None]
    if vars_for_step:
        s.add(Sum([If(v, 1, 0) for v in vars_for_step]) == 1)
    else:
        s.add(False)

def postprocess_negate_unused_assignments_with_model(smt2_filename, assignment_varnames, model, assignment_varmap):
    with open(smt2_filename, encoding="utf-8") as f:
        lines = f.readlines()
    declared = set(assignment_varnames)
    used = set()
    for v in assignment_varnames:
        z3var = assignment_varmap[v]
        try:
            if model.eval(z3var, model_completion=True):
                used.add(v)
        except:
            continue
    negated = set()
    insert_pos = None
    for idx, line in enumerate(lines):
        if "(not assign_" in line:
            import re
            m = re.search(r"\(not (assign_[^\s\)]+)", line)
            if m:
                negated.add(m.group(1))
        if line.strip().startswith("; Step:") and insert_pos is None:
            insert_pos = idx
    if insert_pos is None:
        for idx, line in enumerate(lines):
            if "(assert (!" in line or "(check-sat)" in line:
                insert_pos = idx
                break
        if insert_pos is None:
            insert_pos = len(lines)
    to_negate = declared - used - negated
    if not to_negate:
        print("[Postprocess] Keine weiteren Zuordnungen zu negieren.")
        return
    print(f"[Postprocess] Negiere {len(to_negate)} weitere Zuordnungen im SMT-Modell (basierend auf Modelllösung).")
    negation_lines = []
    negation_lines.append("; Postprocessed negations\n")
    for v in sorted(to_negate):
        negation_lines.append(f"(assert (! (not {v}) :named postproc_neg_{v}))\n")
    negation_lines.append("\n")
    new_lines = lines[:insert_pos] + negation_lines + lines[insert_pos:]
    with open(smt2_filename, "w", encoding="utf-8") as f:
        f.writelines(new_lines)

def is_materialflow_consistent(model, step_resource_to_caps_props, process_steps, resources, recipe, Assignment):
    material_location = {}
    for inp in recipe.get('Inputs', []):
        material_location[inp['ID']] = None
    for interm in recipe.get('Intermediates', []):
        material_location[interm['ID']] = None
    for out in recipe.get('Outputs', []):
        material_location[out['ID']] = None
    step_ids = [step['ID'] for step in process_steps]
    step_by_id = {step['ID']: idx for idx, step in enumerate(process_steps)}
    resource_map = {}
    for i, step in enumerate(process_steps):
        for j, res in enumerate(resources):
            var = Assignment[i][j]
            if var is not None and is_true(model[var]):
                resource_map[step['ID']] = res
    for link in recipe['DirectedLinks']:
        from_id = link['FromID']
        to_id = link['ToID']
        if from_id in step_by_id and to_id in material_location:
            res_of_step = resource_map[from_id]
            caps, _ = step_resource_to_caps_props[step_by_id[from_id]][resources.index(res_of_step)]
            is_transfer = any(c in TRANSPORT_CAPABILITIES for c in caps)
            if is_transfer:
                material_location[to_id] = None
            else:
                material_location[to_id] = res_of_step
            continue
        if from_id in material_location and to_id in step_by_id:
            step_idx = step_by_id[to_id]
            assigned_res = resource_map[to_id]
            caps, _ = step_resource_to_caps_props[step_idx][resources.index(assigned_res)]
            from_res = material_location[from_id]
            is_transfer = any(c in TRANSPORT_CAPABILITIES for c in caps)
            if is_transfer:
                if from_res is None:
                    return False
                if from_res != assigned_res:
                    return False
            else:
                if from_res is not None and from_res != assigned_res:
                    return False
                material_location[from_id] = assigned_res
    return True

def solution_to_json(model, process_steps, resources, step_resource_to_caps_props, Assignment, recipe, capabilities, solution_id):
    """将解决方案转换为JSON格式"""
    solution_data = {
        "solution_id": solution_id,
        "assignments": [],
        "material_flow_consistent": True
    }
    
    for i, step in enumerate(process_steps):
        for j, res in enumerate(resources):
            var = Assignment[i][j]
            if var is not None and is_true(model[var]):
                caps, cap_prop_pairs = step_resource_to_caps_props[i][j]
                
                # 构建步骤分配信息
                assignment_info = {
                    "step_id": step['ID'],
                    "step_description": step['Description'],
                    "resource": res,
                    "capabilities": caps,
                    "parameter_matches": []
                }
                
                # 添加参数匹配信息
                if "Parameters" in step and step["Parameters"]:
                    for param in step["Parameters"]:
                        param_info = {
                            "description": param.get('Description'),
                            "key": param.get('Key'),
                            "unit": param.get('UnitOfMeasure'),
                            "value": param.get('ValueString')
                        }
                        assignment_info["parameter_matches"].append(param_info)
                
                # 添加能力属性匹配信息
                capability_details = []
                for cap_name, matched_props in cap_prop_pairs:
                    cap_info = {
                        "capability_name": cap_name,
                        "matched_properties": []
                    }
                    
                    for param, prop in matched_props:
                        prop_info = {
                            "property_id": prop.get('property_ID'),
                            "property_name": prop.get('property_name'),
                            "property_unit": prop.get('property_unit'),
                        }
                        
                        # 优先检查是否有离散值
                        discrete_values = []
                        for key in prop.keys():
                            if key.startswith('value') and key != 'valueType' and key != 'valueMin' and key != 'valueMax':
                                val = prop.get(key)
                                if val is not None:
                                    try:
                                        # 尝试转换为数字
                                        num_val = float(val)
                                        discrete_values.append(num_val)
                                    except (ValueError, TypeError):
                                        # 如果转换失败，保留原始值
                                        discrete_values.append(val)
                        
                        # 根据属性类型设置值表示
                        value_min = prop.get('valueMin')
                        value_max = prop.get('valueMax')
                        
                        if discrete_values:
                            # 有离散值
                            if len(discrete_values) == 1:
                                # 只有一个离散值，当作具体值
                                prop_info["value"] = discrete_values[0]
                                prop_info["value_type"] = "exact"
                            else:
                                # 多个离散值
                                prop_info["values"] = discrete_values
                                prop_info["value_type"] = "discrete_set"
                        elif value_min is not None or value_max is not None:
                            # 有范围值
                            prop_info["value_min"] = value_min
                            prop_info["value_max"] = value_max
                            prop_info["value_type"] = "range"
                        else:
                            # 没有值信息
                            prop_info["value_type"] = "unspecified"
                        
                        cap_info["matched_properties"].append(prop_info)
                    
                    capability_details.append(cap_info)
                
                assignment_info["capability_details"] = capability_details
                solution_data["assignments"].append(assignment_info)
    
    return solution_data

def print_solution(model):
    print("Combination found:")
    for i, step in enumerate(process_steps):
        for j, res in enumerate(resources):
            var = Assignment[i][j]
            if var is not None and is_true(model[var]):
                caps, cap_prop_pairs = step_resource_to_caps_props[i][j]
                caplist = ', '.join(caps)
                print(f"  - Process step {step['ID']} ('{step['Description']}') -> Resource: {res} (Capabilities: {caplist})")
                param_index_map = {}
                if "Parameters" in step and step["Parameters"]:
                    for idx, param in enumerate(step["Parameters"], start=1):
                        param_id = (param.get('Key'), param.get('UnitOfMeasure'))
                        param_index_map[param_id] = idx
                        print(f"\tRecipe requirement_{idx}: {param['Description']} (Key: {param.get('Key')}, Unit: {param.get('UnitOfMeasure')}, Value: {param.get('ValueString')})")
                for cap_name, matched_props in cap_prop_pairs:
                    print(f"\tCapability '{cap_name}':")
                    property_to_param_idx = {}
                    for param, prop in matched_props:
                        prop_id = (prop.get('property_ID'), prop.get('property_unit'))
                        param_id = (param.get('Key'), param.get('UnitOfMeasure'))
                        idx = param_index_map.get(param_id)
                        if idx:
                            property_to_param_idx[prop_id] = idx
                    cap_obj = None
                    for cap_entry in capabilities[res]:
                        if cap_entry['capability'][0]['capability_name'] == cap_name:
                            cap_obj = cap_entry
                            break
                    if cap_obj is not None:
                        for p_idx, prop in enumerate(cap_obj.get('properties', []), start=1):
                            prop_id = (prop.get('property_ID'), prop.get('property_unit'))
                            discrete_vals = [
                                float(prop[k]) for k in prop.keys()
                                if k.startswith('value') and k != 'valueType' and prop[k] is not None
                            ]
                            value_min = prop.get('valueMin')
                            value_max = prop.get('valueMax')
                            if (value_min is not None or value_max is not None):
                                prop_valstr = f"Range: {value_min}..{value_max}"
                            elif len(discrete_vals) > 1:
                                prop_valstr = f"Discrete values: {', '.join(str(int(v)) if v.is_integer() else str(v) for v in discrete_vals)}"
                            elif len(discrete_vals) == 1:
                                prop_valstr = f"Discrete value: {int(discrete_vals[0]) if discrete_vals[0].is_integer() else discrete_vals[0]}"
                            else:
                                prop_valstr = "(no range or discrete value info)"
                            preconditions = [
                                c for c in prop.get("property_constraint", [])
                                if c.get("conditional_type", "").lower() == "pre"
                            ]
                            for c in preconditions:
                                fulfilled = False
                                fulfilled_by = None
                                step_id = step['ID']
                                input_material_ids = [link['FromID'] for link in recipe['DirectedLinks'] if link['ToID'] == step_id]
                                materials = recipe.get('Inputs', []) + recipe.get('Intermediates', [])
                                input_materials = [mat for mat in materials if mat['ID'] in input_material_ids]
                                for mat in input_materials:
                                    if mat.get('Key') == c.get('property_constraint_ID') and mat.get('UnitOfMeasure') == c.get('property_constraint_unit'):
                                        try:
                                            import re
                                            match = re.match(r'(>=|<=|>|<|=)?\s*([0-9\.,]+)', c.get('property_constraint_value'))
                                            if match:
                                                op, val = match.groups()
                                                op = op or '='
                                                cval = float(val.replace(',', '.'))
                                                mval = float(mat['Quantity'])
                                                if (
                                                    (op == '>=' and mval >= cval) or
                                                    (op == '>' and mval > cval) or
                                                    (op == '<=' and mval <= cval) or
                                                    (op == '<' and mval < cval) or
                                                    (op == '=' and mval == cval)
                                                ):
                                                    fulfilled = True
                                                    fulfilled_by = mat
                                                    break
                                        except Exception:
                                            continue
                                print(f"\t\t\t--> Precondition: {c.get('property_constraint_ID')} ({c.get('property_constraint_unit')}) {c.get('property_constraint_value')} [Resource requirement]")
                                if fulfilled and fulfilled_by:
                                    print(f"\t\t\t    --> fulfilled by: {fulfilled_by.get('ID')} (Key: {fulfilled_by.get('Key')}, Unit: {fulfilled_by.get('UnitOfMeasure')}, Value: {fulfilled_by.get('Quantity')})")
                            if prop_id in property_to_param_idx:
                                ra_idx = property_to_param_idx[prop_id]
                                print(f"\t\t-> Resource property_{p_idx}: {prop.get('property_name')} (Key: {prop.get('property_ID')}, Unit: {prop.get('property_unit')}, {prop_valstr}) [Recipe requirement_{ra_idx}]")
                            else:
                                print(f"\t\t-> Resource property_{p_idx} (not assigned to any recipe requirement): {prop.get('property_name')} (Key: {prop.get('property_ID')}, Unit: {prop.get('property_unit')}, {prop_valstr})")
                    else:
                        print("\t\t[Warning: Capability not found in the capabilities dictionary!]")
    print("-" * 40)

def block_solution(solver, model):
    clause = []
    for i, step_vars in enumerate(Assignment):
        for j, var in enumerate(step_vars):
            if var is not None:
                clause.append(var if is_true(model[var]) else Not(var))
    solver.add(Not(And(clause)))

print("\n==== All possible resource assignments ====")
count = 0
found_model = None
solutions = []  # Storage All Solutions

while s.check() == sat:
    m = s.model()
    if is_materialflow_consistent(m, step_resource_to_caps_props, process_steps, resources, recipe, Assignment):
        print_solution(m)
        found_model = m
        
        # Convert the solution to JSON format and save it.
        solution_json = solution_to_json(m, process_steps, resources, step_resource_to_caps_props, Assignment, recipe, capabilities, count + 1)
        solutions.append(solution_json)
        
        count += 1
    block_solution(s, m)

if count == 0:
    print("No valid combination found! (UNSAT)")
else:
    print(f"Number of combinations found: {count}")
    
    # Save all solutions to a JSON file
    output_filename = "solutions.json"
    with open(output_filename, 'w', encoding='utf-8') as f:
        json.dump({
            "total_solutions": count,
            "solutions": solutions
        }, f, indent=2, ensure_ascii=False)
    
    print(f"All solutions saved to {output_filename}")
    
    # Post-processing is performed only on the first valid solution.
    postprocess_negate_unused_assignments_with_model(
        "smt_model_annotated.smt2", assignment_varnames, found_model, assignment_varmap
    )