# DeepSeek-V4 深度解读：百万上下文背后的工程细节

**Source**: http://mp.weixin.qq.com/s?__biz=MzU5OTM2NjYwNg==&mid=2247516591&idx=1&sn=7bd89bc9c3e7676a61c64a045f511c22&chksm=feb4cf0ec9c34618ccbf278005e6b8928e2050b08f778b28acd5fec7a9093f73925e0d02bc77#rd

点击上方“
Deephub Imba
”,关注公众号,好文章不错过 
!
1M token 上下文设置下，DeepSeek-V4-Pro 的单 token 推理 FLOPs 仅为 DeepSeek-V3.2 的 27%，KV Cache 仅为 V3.2 的 10%；V4-Flash 更激进——FLOPs 10%、KV Cache 7%。百万上下文从演示用 demo，变成了可以日常跑的工作负载。
过去两年大模型的进步基本沿着两条主线：一条是 reasoning 模型靠更长的思考链做 test-time scaling 刷指标；另一条是 agentic 工作流——动辄要处理跨多文档、多工具调用的长 horizon 任务。这两条路都十分需要 context length，而 vanilla attention 是 O(n²) 的：上下文每翻一倍，attention 部分的算力和显存都要翻四倍。这就是为什么大多数开源模型号称 128K，但是到了真实 64K 已经卡顿。
DeepSeek-V4 想解决的正是这个问题，用混合稀疏注意力（CSA + HCA）把 KV Cache 沿序列维度狠压一刀，用 mHC（流形约束的超连接）顶住深层堆叠的数值不稳定，用 Muon 优化器加快收敛，再用 FP4 量化感知训练把 MoE 权重砍一半,这样1M 上下文的边际成本被压到能用的程度。
本文围绕三个问题：长上下文效率到底怎么破（架构）；万亿 MoE 怎么稳定训练（基础设施 + trick）；十几个领域专家如何合并成一个模型（后训练）。
架构：V4 在 V3 之上动了哪三刀
DeepSeek-V4 仍然是 Transformer + DeepSeekMoE + MTP 的底盘，相比 V3 系列做了三处关键升级：
维度
DeepSeek-V3 / V3.2
DeepSeek-V4
注意力
MLA（V3）/ DSA（V3.2）
CSA + HCA 混合
残差连接
标准 residual
mHC（流形约束超连接）
优化器
AdamW
Muon（embedding/head 仍用 AdamW）
MoE 路由
sigmoid + top-k
sqrt(softplus) + 取消节点路由限制
前几层 FFN
dense
MoE + Hash 路由
CSA + HCA —— 把 KV Cache 沿序列维度叠罗汉
V4 的注意力是两种压缩注意力交错的混合架构——CSA（Compressed Sparse Attention）做温和压缩加稀疏选择；HCA（Heavily Compressed Attention）做激进压缩加全量 attention。
CSA：先粗读，再精读
CSA 把每 m 个相邻 token 的 KV 压缩成 1 个压缩 entry（V4-Pro 中 m=4），然后用一个轻量的 Lightning Indexer 给每个 query 选 top-k 个最相关的压缩 entry 做核心 attention（V4-Pro 中 top-k=1024）。
压缩本身是一次加权求和——不是简单平均，用学到的 softmax 权重加位置 bias，相当于让模型自己学这 4 个 token 哪个该多看一点。论文里写得很数学：
 
对每 m 个 token 的 KV，先算两路 C^a, C^b 和对应的权重 Z^a, Z^b
 
softmax 归一化后做加权求和，得到 1 个压缩 entry
这种重叠压缩C^b 用前 m 个 token、C^a 用后 m 个 token是为了避免硬切边界处的信息断裂。
Lightning Indexer 本质是一个低秩多查询的小 attention：用一组专门的 indexer query 对所有压缩后的 indexer key 算分，再 ReLU 加权求和打个分，最后取 top-k。indexer 的 QK 路径全程跑在 FP4 上，是后面 KV Cache 体积能压到 V3.2 的 10% 的关键之一。
一句话总结就是：CSA 等于先把每 m 个 token 摘要成 1 句话，再用一个小模型挑出最相关的 k 句话精读。
HCA：直接做全局摘要
HCA 是另一个极端：压缩比 m' 拉到 128（V4-Pro/Flash 都用 128），不做 overlap，但保留 dense attention，不再 top-k。
为什么需要 HCA？CSA 虽然能精读细节，但 top-k 的稀疏选择天然会漏掉一些全局摘要级的信息。HCA 把 1M tokens 直接压成约 7800 个 entry，所有 query 都能看，相当于一个永远在线的全局摘要通道。
两者交错排布——V4-Pro 前 2 层 HCA、之后 CSA/HCA 交替——构成了一个局部精读加全局浏览的双轨注意力。
几个让效率再上一层的小动作
Partial RoPE 只在 query/KV 的最后 64 维加 RoPE。压缩后的 entry 拿来当 value 时，会带上绝对位置残留；V4 用 position=−i 的 RoPE 在输出端反向贴一次，把绝对位置改回相对位置。
滑窗分支每层额外保留最近 n_win=128 个 token 的未压缩 KV，专门补强局部细节。Attention Sink 给每个 head 加一个可学的 sink logit，让 attention score 总和可以不是 1，甚至接近 0，缓解极长序列下的强制分散注意力问题。KV Cache 走混合精度——RoPE 维度用 BF16、其余维度用 FP8——直接砍半。
把这些组合在一起，论文给出的对比是：以 BF16 GQA8（head_dim=128）为基线，V4 的 KV Cache 能压到约 2%。这就是开篇那个百万上下文能用了的基础保证。
mHC —— 给残差通路套一个概率守恒
DeepSeek-V4 没有沿用标准 residual，而是引入了 mHC（Manifold-Constrained Hyper-Connections）。
先回顾原版 Hyper-Connections：把 residual stream 的宽度从 d 拓宽到 n_hc × d（V4 中 n_hc=4），通过三个映射 A、B、C 控制信息流：
X_{l+1} = B_l X_l + C_l \mathcal{F}_l(A_l X_l)
问题在 B——这是任意学出来的方阵，深堆叠时谱范数容易爆，训练经常崩。
mHC 的关键创新是：把 B 强制约束在 doubly stochastic 矩阵流形（Birkhoff polytope）上。也就是 B 的每行每列都和为 1、元素非负——本质上是个概率混合矩阵。两个直接收益：谱范数小于等于 1，残差变换永远是非膨胀的，前向不会爆、反向梯度不会炸；doubly stochastic 矩阵在乘法下封闭，深堆叠的稳定性可以传递。
实现上，B 的原始参数 \tilde{B} 经过 exp 之后用 Sinkhorn-Knopp 迭代 20 步做行列交替归一化，就投影到了流形上。A、C 则用 sigmoid 限制非负有界。
直觉类比：原版 HC 让残差通路可以做任意线性变换；mHC 把它收紧成概率混合，信息在跨层传递时始终是重新分配，不会被某条路径无限放大或抹掉。相当于给残差通路加了一条信息守恒律。
工程上mHC 增加了激活内存和 pipeline 通信量。论文用三个方法把开销控制住——融合 kernel、选择性重计算、调整 DualPipe 1F1B 重叠——最终额外 wall time 只有 1F1B 的 6.7%。
Muon 优化器
Muon 替换 AdamW 的核心是：不用元素级的二阶矩估计，而是把动量矩阵通过 Newton-Schulz 迭代近似正交化之后再更新。
 
Algorithm: Muon for DeepSeek-V4
 
  G_t  = ∇W L                          # 梯度
 
  M_t  = μ M_{t-1} + G_t                # 动量
 
  O'_t = HybridNewtonSchulz(μ M_t + G_t) # 正交化
 
  O_t  = O'_t · √max(n,m) · γ            # rescale RMS
 
  W_t  = W_{t-1}(1 - ηλ) − η O_t         # 衰减 + 更新
V4 的 hybrid 指 NS 迭代分两段：前 8 步用激进系数 (3.4445, −4.7750, 2.0315) 快速逼近，后 2 步切到保守系数 (2, −1.5, 0.5) 把奇异值精确稳定到 1。
几个细节值得注意。Embedding、prediction head、mHC 的静态 bias 和 RMSNorm 仍然用 AdamW；V4 在 Q、K 上已经加了 RMSNorm，所以不再需要 QK-Clip。ZeRO 兼容性是个工程难题——Muon 需要完整梯度矩阵，跟 ZeRO 的参数切分天然冲突。V4 的方案是 knapsack 算法做 bucket 分配，MoE 参数 flatten 后均匀切分，padding 开销控制在 10% 以内。跨 DP rank 的梯度通信用 BF16（随机舍入），并改成 all-to-all 加本地 FP32 求和的两阶段，避开 BF16 累加误差。
一句话总结：Muon 把找下一步方向从逐元素的 Adam 估计换成对整个梯度矩阵做正交化，方向更稳，收敛更快；但是代价是工程上要重新对齐 ZeRO 流程。
基础设施：让这些设计真的能跑起来
V4 最内卷的部分是它的 infra
 MegaMoE：一个 kernel 把通信和计算全融了
MoE 的瓶颈是 EP（Expert Parallelism）的跨节点 all-to-all。V4 提出按 expert wave 分批调度：把 experts 切成多个 wave，每个 wave 完成通信后立即开始计算；当前 wave 计算、下一个 wave 通信、已完成 wave 的结果回传——三件事并发；整套逻辑融进一个 CUDA mega-kernel（已开源到 DeepGEMM）。
实测在通用推理场景下相比强基线加速 1.5–1.73 倍，RL rollout 和高速 agent 场景能到 1.96 倍。
更有意思的是论文给出的硬件设计建议：通信能不能完全被计算覆盖，本质上由 C/B（peak compute / interconnect bandwidth）决定，而不是单纯堆带宽。对 V4-Pro 来说，C/B ≤ 6144 FLOPs/Byte 即可。这条意见对未来 GPU/NPU 互联设计有现实价值。
TileLang：DSL 替代手写 CUDA
V4 用 TileLang 写大量 fused kernel，Host Codegen 把 host 端的检查、参数 marshalling 全部编译期生成，单次调用 overhead 从几十微秒压到 1 微秒以下。Z3 SMT 求解器辅助形式化整数分析自动验证向量化、内存 hazard、边界条件，把以前需要手工证明才能开的优化全自动化。Bitwise 可复现层面默认关闭 fast-math，提供显式 IEEE-754 intrinsics（T.ieee_fsqrt 等），并对齐 NVCC 的 lowering 顺序。
批不变 + 确定性 kernel：训练-推理 bitwise 对齐
这是个对 RL 训练特别重要的能力。V4 实现了端到端的 batch invariance（任一 token 的输出与它在 batch 中的位置无关）和确定性反向。
Attention 用双 kernel 策略避免 split-KV 引入的 wave-quantization 问题；MatMul 放弃 cuBLAS 改用 DeepGEMM，并放弃 split-k；Attention 反向用每 SM 独立 buffer 加全局确定性 reduction 替代 atomicAdd；MoE 反向通过 token 顺序预处理与 buffer 隔离消除多 rank 写竞争。
当训练和推理 bitwise 一致时，RL 中的采样分布偏移问题被缓解，调试体验也质变。
FP4 QAT：把 MoE 权重再砍一半
V4 在 post-training 阶段对两类参数引入 MXFP4 量化感知训练：MoE 专家权重（GPU 显存大头）、CSA indexer 的 QK 路径（推理热路径）。
在 FP4 → FP8 的 dequant 是无损的：FP8（E4M3）比 FP4（E2M1）多 2 个指数位，只要每个 FP8 量化块（128×128）内部的 FP4 sub-block scale 比值不超阈值，FP4 的 fine-grained scale 就能完全被 FP8 的 dynamic range 吸收。QAT pipeline 可以完全复用现有 FP8 训练框架，反向传播零修改。
推理时直接用真 FP4 权重，避开 simulated quantization 的双倍读写。论文还顺手把 indexer 的 index score 从 FP32 量化到 BF16，top-k selector 加速 2 倍，KV recall 仍有 99.7%。
推理框架：异构 KV Cache 加三档 on-disk 策略
V4 的 KV Cache 是异构的：CSA 有压缩 KV 加 indexer KV，HCA 有更激进的压缩 KV，所有层还有 SWA 滑窗 KV，CSA/HCA 还要管未压缩的尾巴 token。
V4 把 KV Cache 拆成两块。State Cache 定长，存 SWA KV 和未达压缩边界的尾部 token，按 request 预分配。经典 KV Cache 分块，每块覆盖 lcm(m, m')=128 个原始 token，对应 32 个 CSA 压缩 entry 加 1 个 HCA 压缩 entry。
对于共享前缀的请求（典型 RAG 或多轮 agent 场景），V4 把压缩 KV 落盘复用，避免重复 prefill。SWA KV 因为没压缩、体积是 CSA/HCA 的 8 倍，所以提供三档策略：Full（全存）、Periodic（定期 checkpoint）、Zero（不存，靠 CSA/HCA cache 重算最后 n_win·L 个 token），根据存储与算力的比例选择。
训练流程：32T tokens 的预训练加多专家蒸馏
预训练：4K → 1M 的渐进式扩展
数据层面 32T+ tokens，相比 V3 强化了多语言、长文档、数学/代码、agentic 数据；改用 sample-level attention masking，不再是 V3 的 doc-level。课程方面，序列长度按 4K → 16K → 64K → 1M 逐步扩展；attention 也是先 1T tokens 纯 dense，再切到 sparse。
模型规模上，V4-Flash 是 43 层、hidden 4096、256 路由 expert、6 激活、13B activated、284B 总参；V4-Pro 是 61 层、hidden 7168、384 路由 expert、6 激活、49B activated、1.6T 总参。Muon 的 RMS rescale γ 调成 0.18，让 Muon 能复用 AdamW 的学习率超参；峰值 LR 在 Flash 是 2.7e-4，Pro 是 2.0e-4。
训练稳定性：两个机制不明但有效的 trick
万亿 MoE 训练一旦炸 loss，rollback 也救不回来——根因往往是 MoE 层的 outlier 在路由机制下被自我放大。V4 给出两个作者自己也承认理论上还没完全搞清楚的解药。
Anticipatory Routing（前瞻路由）
在第 t 步，用历史参数 θ
{t−Δt} 算路由 index，但用当前参数 θ
t 算 feature。
把 backbone 的更新和 router 的更新解耦，打断 outlier → 路由倾斜 → 更大 outlier 的恶性循环。工程上通过提前 Δt 步预取数据加缓存 routing index，把额外 wall time 控制在约 20%。更聪明的是只在检测到 loss spike 时短暂启用，平稳后切回标准训练，长期开销几乎为零。
SwiGLU Clamping
把 SwiGLU 的 linear 分量 clip 到 [−10, 10]，gate 分量上限 10。简单粗暴，直接抹掉激活 outlier。两个 trick 合用，整个 V4 系列训练再也没崩过。
自媒体角度的看点：DeepSeek 把我们也不完全理解为什么 work 写进正文，请社区一起研究——这种开放姿态在现在的闭源年代越来越稀缺。
后训练：抛弃混合 RL，全面改用 OPD
这是 V4 与 V3.2 最大的方法差异。
V3.2 时代是先 SFT，再 RL，把多个能力混一起训。V4 的 pipeline 改为两步：先做专家培养——对每个领域（数学、代码、agent、指令跟随等）独立做 SFT 加 GRPO RL，得到一组 specialist；再做 OPD 合并——让一个 student 模型在自己采样的 trajectory 上，同时蒸馏所有 specialist 的 logits。
OPD 的 loss 是经典的多教师反向 KL：
\mathcal{L}_{\text{OPD}}(\theta) = \sum_i w_i \cdot D_{\text{KL}}(\pi_\theta \| \pi_{E_i})
关键是 V4 没有用 token-level KL 做简化（虽然省资源但梯度方差大），而是做全词表 logits 蒸馏。十几个 trillion 级教师的 logits 怎么放？V4 的工程方案分四步走：教师权重全部 offload 到分布式存储，按需加载；只缓存最后一层 hidden state，训练时再过 prediction head 重建 logits，避开 100K+ 词表的 logits 物化；按 teacher index 排序数据，确保每个 mini-batch 只加载一次 teacher head；用 TileLang 写专门的 KL 散度 kernel。
这套设计支持几乎无上限的教师数量乘 trillion 级参数。论文承认这种范式比传统混合 RL 更稳定，避开了多目标 RL 的能力互蚀。
推理模式：三档思考预算与交错思考
V4 提供三档：Non-think、Think High、Think Max。三档 RL 时用不同的长度惩罚和上下文窗口训出来；Think Max 用专门的 system prompt 引导深度推理。工具调用场景的 thinking trace 跨用户消息也保留——V3.2 是每个新 user turn 清空——充分利用 1M context。普通对话场景仍然清空，避免 context 膨胀。
另一个工程亮点是 Quick Instruction：把是否触发搜索、意图识别、标题生成这类辅助任务用特殊 token 直接拼到输入末尾，复用已有 KV cache、并行执行。彻底消除主模型旁边再挂一个小模型的工程债。
性能：开源天花板，距前沿闭源仍有 3–6 个月差距
5基础模型层面：V4-Flash-Base 已经吊打 V3.2-Base
13B 激活的 Flash 在大部分指标上已经超过 37B 激活的 V3.2。这个对比把参数数量和参数效率分开，说明 V4 的架构改动有效，不是单纯靠堆参数。
V4-Pro-Max：开源新天花板
亮点摘要：
SimpleQA-Verified 57.9，比所有现有开源模型领先约 20 个百分点，距 Gemini-3.1-Pro（75.6）仍有差距；
Codeforces 3206，人类排名第 23，第一次有开源模型在编程竞赛上和 GPT-5.4（3168）打平甚至略领先；
HMMT 2026 Feb 95.2、IMOAnswerBench 89.8、Apex Shortlist 90.2，数学推理已经摸到第一梯队；
PutnamBench Frontier Regime 取得 120/120 满分，与 Axiom 持平；
1M MRCR 在 1024K 长度仍有 0.59 的 MMR，全程稳定。
Agent 维度上，Terminal Bench 2.0 拿到 67.9（Verified subset 约 72.0）；SWE Verified 80.6，与 Opus-4.6、Gemini-3.1-Pro 同档；BrowseComp 83.4，仅次于 Gemini-3.1-Pro。内部代码 R&D 评测里，DeepSeek-V4-Pro-Max 67% pass rate，超过 Claude Sonnet 4.5（47%），逼近 Opus 4.5（70%）。
现实任务：中文写作和白领任务的胜率
这是论文里最少被讨论但对应该是我们中文用户最有体感的部分。
中文功能性写作对 Gemini-3.1-Pro 的胜率 62.7% 比 34.1%；主要原因是 Gemini 经常用自己的风格偏好覆盖用户的明确要求。创意写作上指令遵循胜率 60.0%、写作质量胜率 77.5%；最难的多轮加复杂指令子集里，Claude Opus 4.5 仍以 52.0% 比 45.9% 胜出。30 项中文白领任务对比 Opus-4.6-Max，综合非负率 63%——V4 在任务完成和内容质量上更强，格式美观还是 Opus 更胜一筹。
Reasoning Effort 的 token 经济学
这张图最有价值的信息是：V4-Pro 在相同 token 预算下，比 V3.2 的 token 效率更高。单位思考 token 换来的性能增益更多。混合稀疏注意力加 Muon 共同作用的结果。
批判性思考：V4 没解决的，和值得追问的
论文自己列了三类 limitation。把它们和我个人的观察合并起来，整理成下面几个值得继续追问的问题。
论文承认的局限
架构复杂度是第一条。CSA 加 HCA 加 mHC 加 Muon 加 FP4 加 Anticipatory Routing 加 SwiGLU Clamping，太多 trick 堆在一起，V4 自己说未来要做减法。机制不明是第二条——Anticipatory Routing 和 SwiGLU Clamping 为什么 work，理论上没讲清楚。第三条是距前沿仍有 3–6 个月差距：reasoning 维度上 V4-Pro-Max 不及 GPT-5.4 与 Gemini-3.1-Pro。
几个值得继续盯的点
CSA 的 top-k=512/1024 是否足够？1M 上下文下，压缩后的 entry 也有约 7800 个，top-k=1024 意味着只看 13%。这个比例在哪些任务上会成为瓶颈，还需要更多消融数据。
mHC 的 Sinkhorn 20 步会不会成为下一个训练瓶颈？每层都要做一次行列归一化迭代，长期是否需要算法层面的近似，论文没给出明确答案。
FP4 QAT 的稳定性边界——目前是 post-training 才引入，pre-training 全程是否可行？这关系到下一代是否能直接 FP4 训练。
OPD 替代 RL 的代价。OPD 本质是离线模仿（轨迹是 on-policy 采样），失去了 RL 在 reward landscape 上的探索能力。在更长 horizon、更稀疏 reward 的任务上是否会吃亏，需要更长时间验证。
Anticipatory Routing 的 Δt 没披露，这个超参的选取本身就值得一篇消融分析。
横向对比同期开源工作
Kimi K2.6 与 GLM-5.1 走的是更标准的稀疏 MoE 加长上下文路线，没有把架构改这么深。Qwen3 与 MiniMax-M2 在 attention 上的探索更保守，但训练数据规模可比。V4 的差异化定位是用更激进的架构换长上下文与推理效率，代价是工程复杂度——短期内别人不容易复刻。
最后总结
DeepSeek-V4 这篇论文最值得记住的，不是某个具体 SOTA 数字，而是它给开源社区贡献的几个可以拿走单独研究的模块：CSA 加 HCA 是长上下文效率的新方向，比 sliding window 或 linear attention 更务实；mHC 给 hyper-connections 装上数学护栏，可能成为下一代 residual 的标配；Muon 加 ZeRO 兼容性方案让非 element-wise 优化器在大规模训练里真正落地；MegaMoE、TileLang、批不变 kernel 这套 infra 哪怕单独拿出来都能撑起一篇系统论文；OPD pipeline 提供了混合 RL 之外的第二条路线——multi-teacher 到 single student 的全词表蒸馏。
更重要的是 DeepSeek 把这些设计的开源实现一并公开——MegaMoE、CSA/HCA inference code、Muon 训练流程都在 huggingface 上能找到。在闭源越来越多、技术报告越来越糊的 2026，这种既写论文又放代码的做法本身就是稀缺品。
V4 是不是开源最强？大部分指标上是。是不是已经追平 GPT-5.4 与 Gemini-3.1-Pro？还差一点，但已经把差距压到了 3–6 个月。
真正的影响在另一面：当百万上下文从贵的玩具变成日常能跑的工作负载，下一波 agentic 应用、长 horizon 任务、在线学习的探索就有了新的基础设施。这才是 V4 系列的分量所在。
喜欢就关注一下吧：
点个 
在看
 你最好看！
 