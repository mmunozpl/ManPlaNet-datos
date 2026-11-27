"""Servidor privado de la prueba de conducta (ZeroGPU).

Carga un solo modelo, el que indican las variables del Space (REPO, REV,
VISION, TAMANO), y devuelve la continuación de textos ya formateados. La
plantilla de conversación la aplica el cliente (conducta.py), no este
servidor. No guarda nada: las respuestas viajan al cliente y solo allí se
escriben.
"""

import json
import os

import gradio as gr
import spaces
import torch
import transformers
from transformers import (AutoModelForCausalLM, AutoModelForImageTextToText,
                          AutoTokenizer)

REPO, REV = os.environ["REPO"], os.environ["REV"]
VISION = os.environ.get("VISION", "1") == "1"
TAMANO = os.environ.get("TAMANO", "large")
DURACION = int(os.environ.get("DURACION", "240"))
TOKEN = os.environ.get("HF_TOKEN")

tok = AutoTokenizer.from_pretrained(REPO, revision=REV, token=TOKEN)
tok.padding_side = "left"
if tok.pad_token is None:
    tok.pad_token = tok.eos_token
clase = AutoModelForImageTextToText if VISION else AutoModelForCausalLM
modelo = clase.from_pretrained(REPO, revision=REV, dtype=torch.bfloat16,
                               token=TOKEN).eval()
modelo.to("cuda")


@spaces.GPU(duration=DURACION, size=TAMANO)
def generar(textos_json: str, max_nuevos: float) -> str:
    """Continúa cada texto con decodificación voraz."""
    textos = json.loads(textos_json)
    enc = tok(textos, return_tensors="pt", padding=True,
              add_special_tokens=False).to("cuda")
    with torch.no_grad():
        out = modelo.generate(**enc, do_sample=False,
                              max_new_tokens=int(max_nuevos),
                              pad_token_id=tok.pad_token_id)
    n = enc["input_ids"].shape[1]
    return json.dumps([tok.decode(o[n:], skip_special_tokens=True)
                       for o in out], ensure_ascii=False)


def info() -> str:
    """Modelo servido y versiones del entorno."""
    return json.dumps(dict(repo=REPO, rev=REV, tamano=TAMANO,
                           torch=torch.__version__,
                           transformers=transformers.__version__,
                           cuda=torch.version.cuda))


with gr.Blocks() as demo:
    t = gr.Textbox(label="textos (JSON)")
    m = gr.Number(value=512, label="tokens nuevos")
    s = gr.Textbox(label="salida")
    gr.Button("generar").click(generar, [t, m], s, api_name="generar")
    gr.Button("info").click(info, None, s, api_name="info")

demo.launch()
