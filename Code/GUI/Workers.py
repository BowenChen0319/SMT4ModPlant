# Code/GUI/Workers.py
import sys
import os
import traceback
from pathlib import Path
from PyQt6.QtCore import QThread, pyqtSignal

try:
    from Code.SMT4ModPlant.GeneralRecipeParser import parse_general_recipe
    from Code.SMT4ModPlant.AASxmlCapabilityParser import parse_capabilities_robust
    from Code.SMT4ModPlant.SMT4ModPlant_main import run_optimization
    from Code.Optimizer.Optimization import SolutionOptimizer
except ImportError as e:
    print("Import Error inside Workers.py: Could not load backend modules.")
    print(f"Specific Error: {e}")

class SMTWorker(QThread):
    """Background thread that handles parsing inputs, running SMT, and optional optimization."""
    log_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int, int)
    # [MODIFIED] Signal now carries (gui_data_list, context_dict)
    finished_signal = pyqtSignal(list, dict)
    error_signal = pyqtSignal(str)

    def __init__(self, recipe_path, resource_dir, mode_index, weights):
        super().__init__()
        self.recipe_path = recipe_path
        self.resource_dir = resource_dir
        self.mode_index = mode_index # 0:SMT(all solutions), 1:OPT(best from multi)
        self.weights = weights 

    def run(self):
        """Execute the end-to-end workflow: parse inputs, solve SMT, optionally rank solutions."""
        try:
            # 1. Parsing
            self.log_signal.emit(f"Parsing Recipe: {self.recipe_path}")
            recipe_data = parse_general_recipe(self.recipe_path)
            self.progress_signal.emit(10, 100)

            # Build list of supported resource files up front to fail fast if empty
            self.log_signal.emit(f"Scanning resource directory: {self.resource_dir}")
            resource_files = [
                f for f in os.listdir(self.resource_dir)
                if f.lower().endswith(('.xml', '.aasx', '.json'))
            ]
            
            if not resource_files:
                raise FileNotFoundError("No .xml or .aasx files found in the selected directory.")

            all_capabilities = {}
            total_files = len(resource_files)
            
            for idx, filename in enumerate(resource_files):
                full_path = os.path.join(self.resource_dir, filename)
                res_name = Path(filename).stem
                self.log_signal.emit(f"Parsing resource file: {filename}")
                
                try:
                    caps = parse_capabilities_robust(full_path)
                    if caps:
                        key_name = f"resource: {res_name}" 
                        all_capabilities[key_name] = caps
                except Exception as parse_err:
                    self.log_signal.emit(f"Warning: Failed to parse {filename}: {parse_err}")

                progress = 10 + int((idx + 1) / total_files * 20)
                self.progress_signal.emit(progress, 100)

            self.log_signal.emit(f"Loaded {len(all_capabilities)} valid resources.")
            if not all_capabilities: raise ValueError("No valid resources loaded.")

            # 2. SMT Logic Configuration
            find_all = True  # SMT lists every solution; OPT also needs the full set before ranking
            is_opt = (self.mode_index == 1)
            
            mode_names = ['SMT (All Solutions)', 'OPT (Best from Multi)']
            self.log_signal.emit(f"Starting SMT Logic (Mode: {mode_names[self.mode_index]})...")
            
            # SMT run
            # Note: run_optimization returns (gui_results, json_solutions)
            # We force generate_json=True internally so we always have data for export, 
            # even in Fast/Pro mode if user wants to export.
            # Wait, user requirement: "Fast" finds 1 solution. 
            # Optimization logic in main: if generate_json=True, it builds the struct.
            # Let's ALWAYS generate the json struct in memory so export works for any valid solution found.
            
            gui_results, json_solutions = run_optimization(
                recipe_data, 
                all_capabilities, 
                log_callback=self.log_signal.emit, 
                generate_json=True, # Always generate structure for export capability
                find_all_solutions=find_all
            )
            
            self.progress_signal.emit(60, 100)

            # 3. OPT Logic: rank all solutions and keep best; SMT just shows all raw solutions
            if is_opt and json_solutions:
                self.log_signal.emit("OPT Mode: Calculating costs and selecting best solution...")
                
                optimizer = SolutionOptimizer()
                optimizer.set_weights(*self.weights)
                optimizer.load_resource_costs_from_dir(self.resource_dir)
                
                evaluated_solutions = optimizer.optimize_solutions_from_memory(json_solutions)
                
                sorted_gui_results = []
                
                for idx, eval_sol in enumerate(evaluated_solutions):
                    sol_id = eval_sol['solution_id']
                    rows = [r for r in gui_results if r.get('solution_id') == sol_id]
                    if sorted_gui_results and rows:
                        sorted_gui_results.append({})  # spacer between solutions
                    
                    for row in rows:
                        row['composite_score'] = eval_sol['composite_score']
                        row['energy_cost'] = eval_sol['total_energy_cost']
                        row['use_cost'] = eval_sol['total_use_cost']
                        row['co2_footprint'] = eval_sol['total_co2_footprint']
                        sorted_gui_results.append(row)
                
                gui_results = sorted_gui_results
                if evaluated_solutions:
                    self.log_signal.emit(f"Optimization complete. Best Solution ID: {evaluated_solutions[0]['solution_id']}")

            self.progress_signal.emit(100, 100)
            
            # [NEW] Pack context for export
            # We need: Resources (all_capabilities), Solutions (json_solutions), General Recipe (recipe_data)
            context_data = {
                'resources': all_capabilities,
                'solutions': json_solutions,
                'recipe': recipe_data
            }
            
            self.finished_signal.emit(gui_results, context_data)

        except Exception as e:
            self.error_signal.emit(str(e))
            self.log_signal.emit(traceback.format_exc())
