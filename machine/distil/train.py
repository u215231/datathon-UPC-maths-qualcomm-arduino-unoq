#!/usr/bin/env python3
"""Fine-tune a small chat model to write a short Python program for a problem (loss on the program tokens only).

    python3 train.py --name coder --base Qwen/Qwen2.5-Coder-1.5B-Instruct --data code_train.jsonl --epochs 3 --save-at 3 --batch 4

Needs a GPU (about 5 minutes on one RTX 4090 for 2,346 examples) and: pip install torch transformers accelerate safetensors.
The first 40 examples of the file are held out, only to print a loss after each epoch."""
import argparse, json, os, random, shutil, time
import torch
from huggingface_hub import snapshot_download
from transformers import AutoTokenizer
BASE = None; REV = None

def load_model(path):
    import transformers
    for cls in ("AutoModelForCausalLM",):
        try:
            return getattr(transformers, cls).from_pretrained(path, torch_dtype=torch.bfloat16)
        except Exception as error:  # noqa: BLE001
            print(f"{cls} failed: {str(error)[:200]}", flush=True)
    raise SystemExit("could not load the model")

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--name", required=True); p.add_argument("--base", required=True); p.add_argument("--data", default="code_train.jsonl")
    p.add_argument("--epochs", type=int, default=6); p.add_argument("--save-at", default="")
    p.add_argument("--lr", type=float, default=1e-5); p.add_argument("--batch", type=int, default=8)
    p.add_argument("--out", default="ckpt")
    a = p.parse_args()
    random.seed(0); torch.manual_seed(0)
    base_dir = snapshot_download(a.base)
    tok = AutoTokenizer.from_pretrained(base_dir)
    pad = tok.pad_token_id if tok.pad_token_id is not None else tok.eos_token_id
    rows = [json.loads(l) for l in open(a.data)]
    ex = []
    for r in rows:
        pi = tok.encode(r["prompt"], add_special_tokens=False); ci = tok.encode(r["completion"], add_special_tokens=False)
        if len(pi) + len(ci) <= 520: ex.append((pi, ci))
    held = ex[:40]; train = ex[40:]
    print(f"{a.name}: {len(train)} training examples, {len(held)} held out; mean completion tokens {sum(len(c) for _, c in ex)/len(ex):.0f}", flush=True)
    model = load_model(base_dir).cuda(); model.train()
    opt = torch.optim.AdamW(model.parameters(), lr=a.lr, weight_decay=0.0)
    steps = a.epochs * ((len(train) + a.batch - 1) // a.batch)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=a.lr, total_steps=steps, pct_start=0.05)
    save_at = {int(x) for x in a.save_at.split(",") if x}

    def loss_of(chunk):
        n = max(len(pi) + len(ci) for pi, ci in chunk)
        ids = torch.full((len(chunk), n), pad); att = torch.zeros((len(chunk), n), dtype=torch.long); lab = torch.full((len(chunk), n), -100)
        for i, (pi, ci) in enumerate(chunk):
            s = pi + ci; ids[i, :len(s)] = torch.tensor(s); att[i, :len(s)] = 1; lab[i, len(pi):len(s)] = torch.tensor(ci)
        ids, att, lab = ids.cuda(), att.cuda(), lab.cuda()
        with torch.autocast("cuda", dtype=torch.bfloat16):
            hidden = model.model(input_ids=ids, attention_mask=att).last_hidden_state
            sel = lab[:, 1:] != -100
            logits = model.lm_head(hidden[:, :-1][sel])
        return torch.nn.functional.cross_entropy(logits.float(), lab[:, 1:][sel])

    @torch.no_grad()
    def held_loss():
        model.eval(); t = [loss_of(held[i:i + 8]).item() for i in range(0, len(held), 8)]; model.train(); return sum(t) / len(t)

    print(f"epoch 0: held-out loss {held_loss():.3f}", flush=True); t0 = time.time()
    for epoch in range(1, a.epochs + 1):
        random.shuffle(train); total = n = 0
        for i in range(0, len(train), a.batch):
            loss = loss_of(train[i:i + a.batch]); loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step(); sched.step(); opt.zero_grad(set_to_none=True); total += loss.item(); n += 1
        print(f"epoch {epoch}: loss {total / n:.3f}, held-out {held_loss():.3f} ({time.time() - t0:.0f} s)", flush=True)
        if epoch in save_at:
            out = f"{a.out}/{a.name}-e{epoch}"
            shutil.copytree(base_dir, out, dirs_exist_ok=True, symlinks=False)
            for f in os.listdir(out):
                if f.endswith(".safetensors") or f == "model.safetensors.index.json": os.remove(os.path.join(out, f))
            model.save_pretrained(out, safe_serialization=True); print("saved", out, flush=True)
    print("TRAIN_DONE", flush=True)

if __name__ == "__main__":
    main()
