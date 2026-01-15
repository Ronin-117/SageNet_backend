import requests
import json
from app.core.config import settings
from app.core.logger import setup_logger

log = setup_logger("LLMService")

class LLMService:
    def __init__(self):
        # Localhost works because we are in Host Mode
        self.api_url = "http://127.0.0.1:11434/api/generate"
        self.model_name = "shopping-guru" 

    def analyze_products(self, query: str, budget: float, products: list, current_device_specs: dict = None):
        """
        1. Formats the One-Shot Prompt.
        2. Sends to Ollama (JSON Mode).
        3. Maps Indices back to Real Products.
        """
        if not products:
            return None

        # 1. Prepare Context (Minified to save tokens)
        # We assign an explicit ID to help the model
        context_list = []
        for i, p in enumerate(products):
            context_list.append({
                "id": i,
                "name": p['name'][:60], # Truncate long names
                "price": p['price'],
                "rating": p['rating'],
                "specs": p['specs'][:120] # Truncate specs
            })
        
        # Prepare Input JSON
        input_data = {
            "query": query,
            "budget": budget,
            "products": context_list
        }
        
        # Add Current Device Context if available (For future anomaly upgrades)
        if current_device_specs:
            input_data["current_device_comparison"] = {
                "note": "Find a better alternative to my current device:",
                "details": current_device_specs
            }
        
        input_json = json.dumps(input_data)

        # 2. Construct Prompt (One-Shot Strategy)
        # We inject a fake example to force the model to behave
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
                "format": "json", # Enforces JSON grammar automatically
                "stream": False,
                "options": {
                    "temperature": 0.2, # Low temp for logic
                    "num_ctx": 4096     # Force context window (From Docs)
                }
            }

            # Extended timeout for 1GB RAM Server (Swap is slow)
            res = requests.post(self.api_url, json=payload, timeout=900)
            
            if res.status_code == 200:
                result_json = res.json()
                ai_text = result_json.get("response", "{}")
                log.info(f"🤖 AI Response: {ai_text[:100]}...") # Log start of response
                
                # Parse AI Output
                try:
                    analysis = json.loads(ai_text)
                except:
                    log.error("AI returned invalid JSON.")
                    return None
                
                # 4. Map Indices back to Full Data (The "Safe" Method)
                ranked_indices = analysis.get("ranked_indices", [])
                final_recommendations = []
                
                for idx in ranked_indices:
                    # Validate index exists in original list
                    if isinstance(idx, int) and 0 <= idx < len(products):
                        # Merge the AI ranking with the ORIGINAL full data
                        # This restores the full Links and Specs that we truncated earlier
                        final_recommendations.append(products[idx])

                # Fallback: If AI returned empty list, return top 3 cheap ones
                if not final_recommendations:
                    final_recommendations = sorted(products, key=lambda x: x['price'])[:3]

                return {
                    "best_choice": analysis.get("best_product_name", "AI Selection"),
                    "reason": analysis.get("reason", "Selected based on price and rating balance."),
                    "recommendations": final_recommendations
                }
            else:
                log.error(f"Ollama Error: {res.text}")
                return None

        except Exception as e:
            log.error(f"LLM Inference Failed: {e}")
            return None

llm_svc = LLMService()