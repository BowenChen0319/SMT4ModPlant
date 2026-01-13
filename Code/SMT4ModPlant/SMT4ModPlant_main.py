import json
from z3 import Solver, Bool, Not, Sum, If, is_true, sat, And

# Global constants
TRANSPORT_CAPABILITIES = ["Dosing", "Transfer", "Discharge"]

# ---------------------------------------------------------
# HELPER FUNCTIONS
# ---------------------------------------------------------

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
            return False, []
    return True, matched_props

def check_preconditions_for_step(recipe, step, cap_entry):
    step_id = step['ID']
    links = recipe.get('DirectedLinks', [])
    input_material_ids = [link['FromID'] for link in links if link.get('ToID') == step_id]
    
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
                    return False
    return True

def has_transfer_capability(res, capabilities_data):
    if res not in capabilities_data:
        return False
    for cap in capabilities_data[res]:
        if cap['capability'][0]['capability_name'] in TRANSPORT_CAPABILITIES:
            return True
    return False

def needs_transfer_to_step(step, current_res_idx, resources, step_by_id, step_resource_to_caps_props, recipe):
    step_id = step['ID']
    links = recipe.get('DirectedLinks', [])
    for link in links:
        if link.get('ToID') == step_id:
            from_id = link['FromID']
            for idx, candidate_step in enumerate(recipe['ProcessElements']):
                if candidate_step['ID'] == from_id:
                    for k, _ in enumerate(resources):
                        if k != current_res_idx:
                            entry = step_resource_to_caps_props[idx][k]
                            if entry and isinstance(entry, tuple) and len(entry) > 0:
                                return True
    return False

def is_materialflow_consistent(model, step_resource_to_caps_props, process_steps, resources, recipe, Assignment):
    material_location = {}
    for inp in recipe.get('Inputs', []):
        material_location[inp['ID']] = None
    for interm in recipe.get('Intermediates', []):
        material_location[interm['ID']] = None
    for out in recipe.get('Outputs', []):
        material_location[out['ID']] = None
        
    step_by_id = {step['ID']: idx for idx, step in enumerate(process_steps)}
    resource_map = {}
    
    for i, step in enumerate(process_steps):
        for j, res in enumerate(resources):
            var = Assignment[i][j]
            if var is not None and is_true(model[var]):
                resource_map[step['ID']] = res
                
    for link in recipe.get('DirectedLinks', []):
        from_id = link['FromID']
        to_id = link['ToID']
        
        if from_id in step_by_id and to_id in material_location:
            if from_id not in resource_map: return False 
            res_of_step = resource_map[from_id]
            step_idx = step_by_id[from_id]
            res_idx = resources.index(res_of_step)
            caps, _ = step_resource_to_caps_props[step_idx][res_idx]
            is_transfer = any(c in TRANSPORT_CAPABILITIES for c in caps)
            if is_transfer:
                material_location[to_id] = None 
            else:
                material_location[to_id] = res_of_step
            continue
            
        if from_id in material_location and to_id in step_by_id:
            if to_id not in resource_map: return False
            assigned_res = resource_map[to_id]
            from_res = material_location[from_id]
            step_idx = step_by_id[to_id]
            res_idx = resources.index(assigned_res)
            caps, _ = step_resource_to_caps_props[step_idx][res_idx]
            is_transfer = any(c in TRANSPORT_CAPABILITIES for c in caps)
            if is_transfer:
                if from_res is None:
                    pass 
                elif from_res != assigned_res:
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

# ---------------------------------------------------------
# EXPORTED FUNCTION (Only this is called by GUI)
# ---------------------------------------------------------

def run_optimization(recipe_data, capabilities_data, log_callback=print):
    process_steps = recipe_data['ProcessElements']
    resources = list(capabilities_data.keys())
    
    log_callback(f"Starting optimization for {len(process_steps)} steps with {len(resources)} resources...")

    step_resource_to_caps_props = [[[] for _ in resources] for _ in process_steps]
    Assignment = []
    step_by_id = {step['ID']: idx for idx, step in enumerate(process_steps)}
    s = Solver()

    # 1. Build Constraints
    for i, step in enumerate(process_steps):
        row = []
        sem_id = step.get('SemanticDescription', "")
        for j, res in enumerate(resources):
            cap_list = capabilities_data[res]
            matching_caps = []
            matching_props = []

            for cap_entry in cap_list:
                is_match = capability_matching(sem_id, cap_entry)
                matched_props_local = []
                if is_match:
                    is_prop_match, matched_props_local = properties_compatible(step, cap_entry)
                    if is_prop_match:
                        if check_preconditions_for_step(recipe_data, step, cap_entry):
                             matching_caps.append(cap_entry['capability'][0]['capability_name'])
                             matching_props.append((cap_entry['capability'][0]['capability_name'], matched_props_local))

            varname = f"assign_{step['ID']}_{res.replace(':', '').replace(' ', '_')}"
            var = Bool(varname)
            
            transfer_needed = needs_transfer_to_step(step, j, resources, step_by_id, step_resource_to_caps_props, recipe_data)
            transfer_cap = has_transfer_capability(res, capabilities_data)

            valid = True
            if transfer_needed and not transfer_cap:
                s.add(Not(var))
                valid = False
            
            if not matching_caps:
                s.add(Not(var))
                valid = False
            
            if valid:
                step_resource_to_caps_props[i][j] = (matching_caps, matching_props)
                row.append(var)
            else:
                row.append(None)
        Assignment.append(row)

    # 2. Uniqueness
    for i, step_vars in enumerate(Assignment):
        vars_for_step = [v for v in step_vars if v is not None]
        if vars_for_step:
            s.add(Sum([If(v, 1, 0) for v in vars_for_step]) == 1)
        else:
            s.add(False)

    # 3. Solve & Retry Loop
    log_callback("Solving constraints...")
    
    def block_solution(solver, current_model):
        true_vars = []
        for row in Assignment:
            for v in row:
                if v is not None and is_true(current_model[v]):
                    true_vars.append(v)
        if true_vars:
            solver.add(Not(And(true_vars)))

    attempt_count = 0
    max_attempts = 200
    
    while s.check() == sat:
        model = s.model()
        attempt_count += 1
        
        if is_materialflow_consistent(model, step_resource_to_caps_props, process_steps, resources, recipe_data, Assignment):
            log_callback(f"Solution Found (Attempt {attempt_count})!")
            
            # # Convert the solution to JSON format and save it.
            # solution_json = solution_to_json(m, process_steps, resources, step_resource_to_caps_props, Assignment, recipe, capabilities, count + 1)
            # solutions.append(solution_json)
            
            results = []
            for i, step in enumerate(process_steps):
                for j, res in enumerate(resources):
                    var = Assignment[i][j]
                    if var is not None and is_true(model[var]):
                        caps, _ = step_resource_to_caps_props[i][j]
                        results.append({
                            "step_id": step['ID'],
                            "description": step['Description'],
                            "resource": res,
                            "capabilities": ", ".join(caps),
                            "status": "Matched"
                        })
            return results
        else:
            log_callback(f"Attempt {attempt_count}: Model SAT, but Material Flow inconsistent. Retrying...")
        
        block_solution(s, model)
            
        if attempt_count >= max_attempts:
            log_callback("Limit reached: Could not find a material-flow consistent solution.")
            break

    log_callback("UNSAT (No Solution Found).")
    return []