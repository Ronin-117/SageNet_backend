import requests
import json
from app.core.config import settings
from app.core.logger import setup_logger

log = setup_logger("LLMService")

class LLMService:
    def __init__(self):
        self.api_url = "http://127.0.0.1:11434/api/generate"
        self.model_name = "shopping-guru" 

    def analyze_products(self, query: str, budget: float, products: list, current_device_specs: dict = None):
        if not products:
            return None

        # 1. Prepare Context
        context_list = []
        for i, p in enumerate(products):
            context_list.append({
                "id": i,
                "name": p['name'][:60],
                "price": p['price'],
                "rating": p['rating'],
                "specs": p['specs'][:120]
            })
        
        input_data = {
            "query": query,
            "budget": budget,
            "products": context_list
        }
        
        if current_device_specs:
            input_data["current_device_comparison"] = {
                "note": "Find a better alternative to:",
                "details": current_device_specs
            }
        
        input_json = json.dumps(input_data)

        # 2. Prompt (One-Shot)
        one_shot = """
<start_of_turn>user
Analyze.
Context: {"products": [{"id": 0, "name": "Bad Item", "price": 5000, "rating": "2.0"}, {"id": 1, "name": "Good Item", "price": 1500, "rating": "4.5"}]}
<end_of_turn>
<start_of_turn>model
{
"ranked_indices": [1, 0],
"best_product_name": "Good Item",
"reason": "Item 1 has significantly better rating and value."
}
<end_of_turn>
"""
        final_prompt = f"{one_shot}<start_of_turn>user\nAnalyze the products. Pick Top 3.\nContext: {input_json}<end_of_turn>\n<start_of_turn>model\n"

        # 3. Call Ollama
        try:
            log.info(f"🧠 Sending {len(products)} items to {self.model_name}...")
            
            payload = {
                "model": self.model_name,
                "prompt": final_prompt,
                "format": "json",
                "stream": False,
                "options": {
                    "temperature": 0.2,
                    "num_ctx": 4096
                }
            }

            res = requests.post(self.api_url, json=payload, timeout=1800)
            
            if res.status_code == 200:
                result_json = res.json()
                ai_text = result_json.get("response", "{}")
                
                try:
                    analysis = json.loads(ai_text)
                    
                    # Validate keys exist
                    if "ranked_indices" not in analysis:
                        analysis["ranked_indices"] = []
                    
                    # OPTIMIZATION: Do NOT expand the objects here.
                    # Just return the raw analysis with indices.
                    return analysis

                except:
                    log.error("AI returned invalid JSON.")
                    return None
            else:
                log.error(f"Ollama Error: {res.text}")
                return None

        except Exception as e:
            log.error(f"LLM Inference Failed: {e}")
            return None

llm_svc = LLMService()