# What Is a LoRA Merge?

## The Anatomy of a LoRA Adapter

A LoRA (Low-Rank Adaptation) adapter is a parameter-efficient fine-tuning technique that keeps a base model's weights frozen and trains only a small, low-rank approximation of the weight updates. For a weight matrix W (d × k), the adapter introduces two trainable matrices: B (d × r) and A (r × k), where r << d is the rank—typically 16 in this project.

During inference, the forward pass computes:

```
h = W·x + (alpha/r)·B·A·x
```

Here, alpha is a scaling hyperparameter (32 in this project), and the division by r normalizes the contribution based on rank. In practice, the scaling factor (alpha/r) = 32/16 = 2, meaning the adapter's contribution is amplified by 2× to compensate for using only 16 dimensions instead of the full 4096-dimensional space.

### Concrete Example: q_proj

For a single projection matrix in Qwen3-8B (q_proj: 4096 × 4096), a LoRA adapter requires (4096 × 16) + (16 × 4096) = 131,072 trainable parameters, versus 16,777,216 for the full matrix—a 99.2% reduction while maintaining comparable expressiveness.

## What "Merge" Actually Does

When you call peft's `merge_and_unload()` (as this project does in `training/win_cuda/src/stoic_training/export.py`), you perform a single computation for each adapted weight matrix:

```
W' = W + (alpha/r)·B·A
```

The result, W', is a plain weight matrix (no adapter machinery) that encodes both the base knowledge and the task-specific adaptation. The model is then saved via `save_pretrained()` as a standard HuggingFace checkpoint using safetensors format.

**Mathematical equivalence**: At inference time, the merged model `h = W'·x` is mathematically identical to the base model with adapter `h = W·x + (alpha/r)·B·A·x`. Both compute the same output for a given input.

### The QLoRA Caveat

There is one subtle but important difference: during training, this project quantizes the base model to 4-bit NF4 (nf4 in bitsandbytes) to fit within GPU memory, so the forward passes during training used 4-bit weights (activations remain bf16). However, `merge_and_unload()` folds the adapter into the *original bf16 base weights* (as loaded in export.py), not the quantized versions the training process observed. This means the merged model's outputs will differ slightly from what the trained (quantized) model actually saw during training—not because of a bug, but because you are now computing with full-precision weights instead of quantized ones.

## Why Merge?

**Self-contained artifact**: A merged model is a complete, standalone checkpoint requiring no external adapter files or peft machinery at inference. This simplifies deployment significantly.

**No runtime dependency**: Inference frameworks do not need peft installed; they only need transformers.

**Prerequisite for GGUF conversion**: llama.cpp's `convert_hf_to_gguf.py` (invoked by export.py) only understands plain model checkpoints. It cannot ingest a base model + separate adapter; you must merge first.

**LM Studio compatibility**: Once converted to GGUF format (the next step in this repo's pipeline), merged models load directly into LM Studio without adapter configuration.

## Trade-off: Merged vs. Adapter-Separate

Keeping adapters separate has advantages: a single LoRA adapter is 100–200 MB, while a merged Qwen3-8B model in bf16 is ~16 GB. If you want to experiment with multiple task-specific adapters on the same base, deploying them separately and swapping adapters at runtime avoids storing multiple full-size models.

For this project, merge is the default because a single, portable artifact matters more than adapter modularity.

## Pipeline in This Repository

The export flow (in `training/win_cuda/src/stoic_training/export.py`) is:

1. Load base model (bf16, device_map="auto") and LoRA checkpoint
2. Call `PeftModel.from_pretrained()` to attach the adapter
3. Call `merge_and_unload()` to fold the adapter into W
4. Call `model.save_pretrained()` to write safetensors
5. Optionally, if `--llama-cpp-dir` is provided, invoke `convert_hf_to_gguf.py` to produce a GGUF file
6. Record export artifacts (paths and SHA256 hashes) in the run's manifest.json

Without `--llama-cpp-dir`, the process stops after step 4; the merged checkpoint is ready for standard transformers inference.

## Further Reading

- **LoRA paper**: "LoRA: Low-Rank Adaptation of Large Language Models" (Hu et al., 2021). Available on arXiv at https://arxiv.org/abs/2106.09685
- **QLoRA paper**: "QLoRA: Efficient Finetuning of Quantized LLMs" (Dettmers et al., 2023). Available on arXiv at https://arxiv.org/abs/2305.14314
- **HuggingFace PEFT documentation on merging**: https://huggingface.co/docs/peft/main/en/developer_guides/lora (see "Merge LoRA weights")
- **bitsandbytes NF4 quantization docs**: https://github.com/bitsandbytes-foundation/bitsandbytes (see quantization documentation in the repository)
- **llama.cpp convert_hf_to_gguf.py**: https://github.com/ggml-org/llama.cpp/blob/master/convert_hf_to_gguf.py
