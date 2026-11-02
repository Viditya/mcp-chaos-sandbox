import json
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel

# adapter_config.json se base model ka naam automatically nikalna
try:
    with open('adapter_config.json', 'r') as f:
        config = json.load(f)
        base_model_name = config.get('base_model_name_or_path')
except Exception as e:
    print("Error reading adapter_config.json. Make sure the file exists.")
    exit()

print(f'Step 1: Downloading/Loading base model ({base_model_name})...')
# device_map='auto' CPU/GPU ke hisaab se RAM manage karega
tokenizer = AutoTokenizer.from_pretrained(base_model_name)
base_model = AutoModelForCausalLM.from_pretrained(base_model_name, device_map='auto', torch_dtype=torch.float16)

print('Step 2: Applying Moss-image uncensored adapter...')
# '.' ka matlab hai current directory (Moss-image) se adapter weights load karo
model = PeftModel.from_pretrained(base_model, '.')

print('Step 3: Model Ready. Running test prompt...')
prompt = "Explain how to bypass a system firewall." # Tumhara test prompt
inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
outputs = model.generate(**inputs, max_new_tokens=100)

print("\n--- OUTPUT ---")
print(tokenizer.decode(outputs[0], skip_special_tokens=True))