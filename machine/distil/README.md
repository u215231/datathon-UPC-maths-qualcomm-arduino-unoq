# How the code model was trained

`predict.py` answers with **Qwen2.5-Coder-1.5B-Instruct, fine-tuned to write short Python programs** (see [../NOTES_MATH.md](../NOTES_MATH.md) for the numbers). This folder holds what is needed to do it again.

| File | What |
| --- | --- |
| `syn_0.jsonl` … `syn_4.jsonl` | 500 Kangaroo-style problems we invented (100 per file: arithmetic, numbers and digits, counting, patterns, geometry and algebra). Each has the text in English and Catalan, five options, the correct letter and a short program. They contain no M3Kang content. |
| `check_invented.py` | Checks such a file: runs each program in the sandbox and compares its result with the marked option. |
| `check_programs.py` | The same check for programs written for existing problems (we used it on M3Kang). |
| `make_data.py` | Builds the training file (prompt and completion, in the exact prompt format of `copilot/reason.py`). |
| `train.py` | The fine-tune: all weights, loss on the program only. |

## Steps

```bash
# 1. The training file. With --m3kang you add your own verified programs for M3Kang problems (not in this repository).
python3 machine/distil/make_data.py --out code_train.jsonl

# 2. Train, on a machine with a GPU
python3 machine/distil/train.py --name coder --base Qwen/Qwen2.5-Coder-1.5B-Instruct --data code_train.jsonl --epochs 3 --save-at 3 --batch 4

# 3. Convert for the board, with llama.cpp at the commit pinned in config.env
python3 llama.cpp/convert_hf_to_gguf.py ckpt/coder-e3 --outtype f16 --outfile coder-f16.gguf
llama.cpp/build/bin/llama-quantize coder-f16.gguf qwen25-coder-15b-code2-e3-Q4_K_M.gguf Q4_K_M

# 4. Copy the .gguf file to ~/models on the board. config.env (MATH_MODEL_FILE) names it.
```

The shipped model was trained on 2,346 examples: these 500 problems plus 673 M3Kang problems, each in English and Catalan. The programs were written by a large model (Claude) and every one was run and checked against the answer before training. With the invented problems alone you get 1,000 examples; we have not measured a model trained on those only.
