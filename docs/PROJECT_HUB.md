# Arduino Project Hub write-up (paste into projecthub.arduino.cc)

**Title:** Uino: an offline maths tutor owl on the Arduino UNO Q

## Introduction

Uino is a small owl that helps students aged 10 to 18 practise Kangaroo (Cangur) maths competition problems. It never just gives the answer: it offers hints, one step at a time, in Catalan or English. Everything runs on an Arduino UNO Q 4 GB inside a 3D-printed owl, with no internet, so it works in any classroom and nothing a student types leaves the device. The owl's eyes are the board's LED matrix.

*(photo or 20-second video of the owl here)*

## Components and apps

- Arduino UNO Q 4 GB, USB-C power
- Arduino App Lab (the LED-eyes app)
- llama.cpp (pinned commit in `config.env`)
- Models: Qwen3.5 0.8B (coach), bge-small-en-v1.5 (similar problems), Qwen2.5-Math 1.5B fine-tuned by us (writes programs)
- A 3D-printed owl shell

## Architecture

*(the diagram from the README)*

The Linux side runs three llama.cpp servers and one small Python web server. The student opens the page from a laptop or phone. The STM32 microcontroller draws the eyes; the Linux side tells it which animation to play over the Arduino Bridge.

- **Teach:** the student answers a problem. If it's wrong, Uino says "not yet" and offers hints: a similar, easier problem from the bank; a way to start; Uino's own idea; and the solution only at the end. Every hint is a lookup or was written and checked ahead of time, so it appears at once. The level goes up or down with the student.
- **Reason:** Uino answers a problem by itself in under 60 seconds. A small maths model writes a short Python program, the board runs it in a sandbox, and the result is matched to one of the options. You can watch the program being written.

## Step by step

1. **Set up the board** with steps 0 to 12 of the setup guide in the repository (`docs/SETUP_GUIDE.md`): build llama.cpp, download the two base models, start the two services, build the problem index. You should see `{"status":"ok"}` from `curl http://127.0.0.1:8081/health`.
2. **Get the code:** `git clone https://github.com/u215231/datathon-UPC-maths-qualcomm-arduino-unoq.git ~/uino && cd ~/uino`
3. **(Optional) the maths model:** put `qwen25-math-15b-code-e3-Q4_K_M.gguf` in `~/models`. `machine/NOTES_MATH.md` explains how we made it. Without it, Uino answers with the smaller model.
4. **Install:** `bash owl/install.sh`. It builds the problem bank, compiles and flashes the eyes, and makes everything start at boot. About 3 minutes, no sudo. You should see "Done. Uino is at http://…:8000".
5. **Open the page** at `http://<board-ip>:8000` from a device on the same network, or over USB with `adb forward tcp:8000 tcp:8000` and `http://127.0.0.1:8000`.
6. **Unplug it and plug it in again.** The eyes wake up, and the page comes back by itself.
7. **Check it:** `python3 coach/check.py http://<board-ip>:8000 --api=/api/coach` plays a student through 27 checks.

Full code and details: the GitHub repository.

## Results and error analysis

On the organisers' practice set (100 problems, where guessing gets 20), measured on the board:

- The starter pipeline, one letter from the 0.8B model: 22.
- Bigger general models (2B, 4B): 21 and 22, and the 4B is too slow.
- The 0.8B writing a Python program: 27.
- **Uino, the maths model trained to write short programs: 33**, with every answer in under 50 seconds.

When Uino's program matches an option, it is right about two times in three (19 of 30). When it doesn't, the answer is a letter guess, and those are no better than chance. English and Catalan score the same.

## What we learned

- On this board a model reads 5 to 11 tokens a second and writes 3 to 6, so the budget is about 100 tokens of writing. Short programs fit; reasoning in words doesn't.
- A small model can't learn maths from answer letters. Fine-tuned on problem → letter, it memorised the bank and stayed at chance on new problems. Fine-tuned on problem → short program, it improved on problems it had never seen.
- Small models write poor hints. Uino's hints are lookups, hand-written advice, or model text checked in code, and a wrong answer never reveals the solution.
- Next: answers that are names or times, problems with figures, and a teacher's review of the model-written hints.

M3Kang (the problem bank) is for research use only, so no problem text or derived model is published with the project. Dataset: https://huggingface.co/datasets/qualcomm/M3Kang
