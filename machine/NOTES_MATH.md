# The maths model (Reason)

`REASON_STRATEGY=math` answers with **Qwen2.5-Math-1.5B-Instruct, fine-tuned by us to write short Python programs**.

Why: untuned, the maths model writes good programs but long ones (about 350 tokens with its explanations), and the board writes 3 tokens a second. Trained on short programs, it writes about 44 tokens.

How it was made (15 Nov 2026):
1. For the 734 M3Kang problems that need no figure and have numeric options, a large model wrote a short program (at most 12 lines, no comments). We ran every program in our sandbox and kept the 673 whose result equals the correct option.
2. Each program became two training examples, with the English and the Catalan text: 1,346 examples in the exact prompt format of `copilot/reason.py` (`math_prompt`).
3. Full fine-tune, 3 epochs, learning rate 1e-5, batch 4, on one RTX 4090 (about 3 minutes). Converted to GGUF and quantised to Q4_K_M (986 MB) with llama.cpp at the pinned commit.

The model file (`qwen25-math-15b-code-e3-Q4_K_M.gguf`) goes in `~/models` on the board. It is not in this repository: it is derived from M3Kang, which is for research use only. `predict.py` starts its llama-server on `MATH_PORT` when it isn't running, next to the two services; if the file is missing, the 0.8B pipeline answers instead.

Measured on the organisers' practice set (100 rows, chance 20%):

| Pipeline | Board | Laptop |
| --- | --- | --- |
| 0.8B: letter + Python + balancing | 27% | 35% |
| Maths model, tuned: Python + letter + balancing | 32% | 43% |

On the board the tuned model's program matched an option on 30 problems and was right on 19; mean 34.8 s, max 49.4 s per problem. Speeds on the board: reads 5.1 tokens/s, writes 3.0.
