# solution_optimizer.py
import json
import os
from typing import Dict, List, Any
import xml.etree.ElementTree as ET

class SolutionOptimizer:
    def __init__(self):
        self.weights = {
            "EnergyCost": 0.4,
            "UseCost": 0.3,
            "CO2Footprint": 0.3
        }
        self.resource_costs = {}  # Dictionary to store resource cost data
    
    def set_weights(self, energy_weight, use_weight, co2_weight):
        """Set custom weights"""
        total = energy_weight + use_weight + co2_weight
        self.weights = {
            "EnergyCost": energy_weight / total,
            "UseCost": use_weight / total,
            "CO2Footprint": co2_weight / total
        }
    
    def extract_resource_cost_data(self, xml_file_path: str) -> Dict[str, float]:
        """Extract resource cost data from AAS XML file"""
        try:
            tree = ET.parse(xml_file_path)
            root = tree.getroot()
            
            # Initialize cost data
            cost_data = {
                "EnergyCost": 0.0,
                "UseCost": 0.0,
                "CO2Footprint": 0.0
            }
            
            # Find OptimizationCost submodel
            for submodel in root.findall('.//{*}submodel'):
                id_short = submodel.find('{*}idShort')
                if id_short is not None and id_short.text == 'OptimizationCost':
                    # Found optimization cost submodel, extract property values
                    for prop in submodel.findall('.//{*}property'):
                        prop_id = prop.find('{*}idShort')
                        value_elem = prop.find('{*}value')
                        
                        if prop_id is not None and value_elem is not None:
                            prop_name = prop_id.text
                            if prop_name in cost_data:
                                try:
                                    cost_data[prop_name] = float(value_elem.text)
                                except (ValueError, TypeError):
                                    print(f"Warning: Unable to parse value for {prop_name}: {value_elem.text}")
                                    cost_data[prop_name] = 0.0
            
            return cost_data
            
        except ET.ParseError as e:
            print(f"XML parsing error {xml_file_path}: {e}")
            return None
        except Exception as e:
            print(f"Error processing file {xml_file_path}: {e}")
            return None
    
    def load_all_resource_costs(self, resource_files: List[str]):
        """Load cost data for all resources"""
        for file_path in resource_files:
            if not os.path.exists(file_path):
                print(f"File not found: {file_path}")
                continue
                
            # Extract resource name from filename (e.g., HC11.xml -> HC11)
            resource_name = os.path.splitext(os.path.basename(file_path))[0]
            print(f"Loading resource cost data: {resource_name}")
            
            cost_data = self.extract_resource_cost_data(file_path)
            if cost_data:
                self.resource_costs[resource_name] = cost_data
                print(f"  - Energy Cost: {cost_data['EnergyCost']}")
                print(f"  - Use Cost: {cost_data['UseCost']}")
                print(f"  - CO2 Footprint: {cost_data['CO2Footprint']}")
            else:
                print(f"  - Unable to extract cost data")
    
    def calculate_solution_cost(self, solution: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate total cost for a single solution"""
        total_energy_cost = 0.0
        total_use_cost = 0.0
        total_co2_footprint = 0.0
        resource_usage = {}
        
        # Count usage and cost for each resource
        for assignment in solution['assignments']:
            # Extract resource name from resource string (e.g., "resource: HC20" -> "HC20")
            resource_str = assignment['resource']
            resource_name = resource_str.split(': ')[1] if ': ' in resource_str else resource_str
            
            if resource_name in self.resource_costs:
                cost_data = self.resource_costs[resource_name]
                total_energy_cost += cost_data['EnergyCost']
                total_use_cost += cost_data['UseCost']
                total_co2_footprint += cost_data['CO2Footprint']
                
                # Record resource usage
                if resource_name in resource_usage:
                    resource_usage[resource_name] += 1
                else:
                    resource_usage[resource_name] = 1
            else:
                print(f"Warning: Resource {resource_name} in solution {solution['solution_id']} has no cost data")
        
        # Calculate weighted composite score
        composite_score = (
            total_energy_cost * self.weights["EnergyCost"] +
            total_use_cost * self.weights["UseCost"] +
            total_co2_footprint * self.weights["CO2Footprint"]
        )
        
        return {
            "solution_id": solution['solution_id'],
            "total_energy_cost": total_energy_cost,
            "total_use_cost": total_use_cost,
            "total_co2_footprint": total_co2_footprint,
            "composite_score": composite_score,
            "resource_usage": resource_usage,
            "material_flow_consistent": solution['material_flow_consistent'],
            "weighted_breakdown": {
                "energy": total_energy_cost * self.weights["EnergyCost"],
                "use": total_use_cost * self.weights["UseCost"],
                "co2": total_co2_footprint * self.weights["CO2Footprint"]
            }
        }
    
    def optimize_solutions(self, solutions_file: str, resource_files: List[str]) -> List[Dict[str, Any]]:
        """Optimize solutions"""
        print("=" * 60)
        print("Starting Solution Optimization")
        print("=" * 60)
        
        # 1. Load cost data for all resources
        print("\nStep 1: Loading Resource Cost Data")
        print("-" * 40)
        self.load_all_resource_costs(resource_files)
        
        if not self.resource_costs:
            print("Error: No resource cost data found")
            return []
        
        # 2. Load solutions
        print(f"\nStep 2: Loading Solutions File: {solutions_file}")
        print("-" * 40)
        try:
            with open(solutions_file, 'r', encoding='utf-8') as f:
                solutions_data = json.load(f)
            
            solutions = solutions_data['solutions']
            print(f"Found {len(solutions)} solutions")
            
        except Exception as e:
            print(f"Error loading solutions file: {e}")
            return []
        
        # 3. Calculate cost for each solution
        print(f"\nStep 3: Calculating Solution Costs")
        print("-" * 40)
        evaluated_solutions = []
        
        for solution in solutions:
            print(f"Calculating cost for solution {solution['solution_id']}...")
            cost_result = self.calculate_solution_cost(solution)
            evaluated_solutions.append(cost_result)
            
            print(f"  - Total Energy Cost: {cost_result['total_energy_cost']:.2f}")
            print(f"  - Total Use Cost: {cost_result['total_use_cost']:.2f}")
            print(f"  - Total CO2 Footprint: {cost_result['total_co2_footprint']:.2f}")
            print(f"  - Composite Score: {cost_result['composite_score']:.2f}")
        
        # 4. Sort by composite score (lower is better)
        evaluated_solutions.sort(key=lambda x: x["composite_score"])
        
        return evaluated_solutions
    
    def find_optimal_solution(self, solutions: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Find optimal solution"""
        if not solutions:
            return None
        
        optimal = solutions[0]  # Already sorted by score, first is optimal
        
        print("\n" + "=" * 60)
        print("🏆 Optimal Solution Found!")
        print("=" * 60)
        print(f"Optimal Solution ID: {optimal['solution_id']}")
        print(f"Composite Score: {optimal['composite_score']:.2f}")
        print("\nTotal Cost Details:")
        print(f"  - Total Energy Cost: {optimal['total_energy_cost']:.2f}")
        print(f"  - Total Use Cost: {optimal['total_use_cost']:.2f}")
        print(f"  - Total CO2 Footprint: {optimal['total_co2_footprint']:.2f}")
        print(f"\nWeighted Breakdown:")
        print(f"  - Energy Contribution: {optimal['weighted_breakdown']['energy']:.2f}")
        print(f"  - Use Contribution: {optimal['weighted_breakdown']['use']:.2f}")
        print(f"  - CO2 Contribution: {optimal['weighted_breakdown']['co2']:.2f}")
        print(f"\nResource Usage:")
        for resource, count in optimal['resource_usage'].items():
            print(f"  - {resource}: Used {count} times")
        print(f"\nWeights Used: {self.weights}")
        
        return optimal
    
    def generate_optimization_report(self, solutions: List[Dict[str, Any]], output_file: str = "optimization_report.json"):
        """Generate optimization report"""
        report = {
            "optimization_date": "2024-01-01",  # Can be updated to actual date
            "weights_used": self.weights,
            "total_solutions_evaluated": len(solutions),
            "resource_costs_available": list(self.resource_costs.keys()),
            "results": solutions,
            "optimal_solution": solutions[0] if solutions else None
        }
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        
        print(f"\nOptimization report saved to: {output_file}")
        return report

def main():
    # Initialize optimizer
    optimizer = SolutionOptimizer()
    
    # Set resource files (AAS files) to analyze
    resource_files = [
    "2025-04_HC10.xml",
    "2025-04_HC11.xml",
    "2025-04_HC12.xml",
    "2025-04_HC13.xml",
    "2025-04_HC14.xml",
    "2025-04_HC15.xml",
    "2025-04_HC16.xml",
    "2025-04_HC17.xml",
    "2025-04_HC18.xml",
    "2025-04_HC19.xml",
    "2025-04_HC20.xml",
    "2025-04_HC21.xml",
    "2025-04_HC22.xml",
    "2025-04_HC23.xml",
    "2025-04_HC24.xml",
    "2025-04_HC25.xml",
    "2025-04_HC26.xml",
    "2025-04_HC27.xml",
    "2025-04_HC28.xml",
    "2025-04_HC29.xml",
    "2025-04_HC30.xml",
    "2025-04_HC31.xml",
    "2025-04_HC32.xml",
    "2025-04_HC33.xml",
    "2025-04_HC34.xml",
    "2025-04_HC35.xml",
    "2025-04_HC36.xml",
    "2025-04_HC37.xml",
    "2025-04_HC38.xml",
    "2025-04_HC39.xml",
    ]
    
    # Solutions file
    solutions_file = "solutions.json"
    
    # Optimize solutions
    results = optimizer.optimize_solutions(solutions_file, resource_files)
    
    if not results:
        print("No solutions successfully evaluated")
        return
    
    # Find optimal solution
    optimal = optimizer.find_optimal_solution(results)
    
    # Generate detailed report
    optimizer.generate_optimization_report(results)
    
    # Display ranking
    print("\n" + "=" * 50)
    print("Solution Ranking:")
    print("=" * 50)
    for i, result in enumerate(results, 1):
        print(f"{i}. Solution {result['solution_id']} - Score: {result['composite_score']:.2f}")

if __name__ == "__main__":
    main()