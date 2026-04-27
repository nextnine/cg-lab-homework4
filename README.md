# 计算机图形学实验四：基于 Taichi 的 Phong/Blinn-Phong 光照与硬阴影

本项目使用 **Taichi + Ray Casting** 从零构建一个代码驱动的三维场景，并在每像素级别实现：

- 局部光照模型（Ambient / Diffuse / Specular）；
- 射线与几何体求交及深度竞争（最近交点）；
- 可交互的材质参数调节（Ka / Kd / Ks / Shininess）；
- 选做拓展：Blinn-Phong 与硬阴影（Shadow Ray）。

---

## 1. 实验目标

### 1.1 理论理解
理解并掌握局部光照模型的三个核心分量：

- **Ambient（环境光）**：场景背景能量的近似；
- **Diffuse（漫反射）**：满足 Lambert 余弦规律；
- **Specular（镜面高光）**：与观察方向相关的高光反射。

### 1.2 数学基础
熟练掌握以下向量计算：

- 法向量 $\mathbf{N}$ 的构造与归一化；
- 光线方向 $\mathbf{L}$、视线方向 $\mathbf{V}$；
- 反射向量 $\mathbf{R}$ 或半程向量 $\mathbf{H}$；
- 点乘截断 $\max(0,\cdot)$ 与颜色范围钳制 clamp。

### 1.3 工程实践
基于 `ti.ui.Window` 实现实时交互，通过滑动条动态修改光照参数并观察画面变化。

---

## 2. 实验原理

Phong 光照模型：

$$
I = I_{ambient} + I_{diffuse} + I_{specular}
$$

环境光：

$$
I_{ambient} = K_a \cdot C_{light} \cdot C_{object}
$$

漫反射：

$$
I_{diffuse} = K_d \cdot \max(0, \mathbf{N} \cdot \mathbf{L}) \cdot C_{light} \cdot C_{object}
$$

镜面高光（Phong 形式）：

$$
I_{specular} = K_s \cdot \max(0, \mathbf{R} \cdot \mathbf{V})^n \cdot C_{light}
$$

变量含义：

- $\mathbf{N}$：表面法向量
- $\mathbf{L}$：指向光源方向
- $\mathbf{V}$：指向相机方向
- $\mathbf{R}$：理想反射方向
- $n$：高光指数（Shininess）

---

## 3. 场景与参数设置（对应代码实现）

### 3.1 几何体（Ray Casting 隐式建模）

1. **红色球体**
   - 圆心：`(-1.2, -0.2, 0)`
   - 半径：`1.2`
   - 基础色：`(0.8, 0.1, 0.1)`

2. **紫色圆锥**
   - 顶点：`(1.2, 1.2, 0)`
   - 底面高度：`y = -1.4`
   - 底半径：`1.2`
   - 基础色：`(0.6, 0.2, 0.8)`

> 当前代码还加入了地面平面（棋盘格）用于增强遮挡与阴影可视效果。

### 3.2 摄像机与光源

- 摄像机位置（射线起点）：`(0, 0, 5)`
- 点光源位置：`(2, 3, 4)`
- 光源颜色：`(1.0, 1.0, 1.0)`
- 背景颜色：深青色

---

## 4. 任务实现说明

### 任务 1：构建代码驱动三维场景

通过 `intersect_sphere`、`intersect_cone`、`intersect_plane` 三个函数，分别完成球体、圆锥、平面的光线求交，完全不依赖外部模型文件。

### 任务 2：实现求交与深度测试

在 `intersect_scene` 中对多个几何体分别求交，采用“保留最小正 t”的方式实现类似 Z-buffer 的深度竞争逻辑：

- 若射线同时命中多个物体，选择离相机最近者；
- 返回命中法向量、材质颜色、物体 ID；
- 在 `render` 中据此完成正确遮挡。

### 任务 3：编写 Phong 着色器

命中点处计算：

- $\mathbf{L}=\text{normalize}(light\_pos-p)$
- $\mathbf{V}=\text{normalize}(ro-p)$
- Phong 反射向量（数学表达）：

$$
\mathbf{R} = 2(\mathbf{N} \cdot \mathbf{L})\mathbf{N} - \mathbf{L}
$$

  代码实现：`reflect(-L, N)`

随后累加 Ambient、Diffuse、Specular，并在写入像素前执行：

- `ti.max(0.0, dot)` 截断背光负值；
- `ti.math.clamp(color, 0.0, 1.0)` 限制颜色范围。

### 任务 4：UI 交互面板

使用 `ti.ui.Window` + `gui.slider_float` 提供 4 个实时参数：

1. **Ka (Ambient)**：`0.0 ~ 1.0`，默认 `0.2`
2. **Kd (Diffuse)**：`0.0 ~ 1.0`，默认 `0.7`
3. **Ks (Specular)**：`0.0 ~ 1.0`，默认 `0.5`
4. **Shininess**：`1.0 ~ 128.0`，默认 `32.0`

此外还提供两个勾选框（选做功能）：

- `Use Blinn-Phong`
- `Enable Hard Shadow`

---

## 5. 选做内容实现

### 5.1 Blinn-Phong 升级

启用后以半程向量 $\mathbf{H}=\text{normalize}(\mathbf{L}+\mathbf{V})$ 计算高光：

$$
I_{specular}^{Blinn} = K_s \cdot \max(0, \mathbf{N}\cdot\mathbf{H})^n \cdot C_{light}
$$

**现象对比（简述）**：

- Blinn-Phong 在大入射角下高光更稳定，边缘过渡通常更自然；
- Phong 的高光位置更“尖锐”，在某些角度可能更容易出现高光收缩。

### 5.2 硬阴影（Hard Shadow）

在命中点处沿光源方向发射 shadow ray：

- 若在到达光源前再次命中物体，则判定为阴影；
- 阴影区仅保留 Ambient 分量；
- 非阴影区使用完整光照 `ambient + diffuse + specular`。

---

## 6. 运行方法

### 6.1 环境准备

```bash
pip install taichi
```

### 6.2 启动程序

```bash
python main.py
```

运行后会弹出窗口，右侧面板可实时调节参数并观察光照变化。

---

## 7. 常见问题排查

1. **画面全黑或异常乱码**
   - 检查向量是否归一化（$\mathbf{N}$、$\mathbf{L}$、$\mathbf{V}$ 必须单位化）。

2. **黑色噪点/马赛克**
   - 确认漫反射和高光使用了 `ti.max(0.0, dot)`。

3. **颜色过曝发白**
   - 写入像素前必须 `clamp` 到 `[0, 1]`。

---

## 8. 运行结果

> 请在此处放置实验运行结果（视频或 GIF）。

- 示例：`results/phong_demo.gif`
- 示例：`results/phong_demo.mp4`

你也可以直接在 README 中嵌入 GIF：

```markdown
![Phong 实验效果](results/phong_demo.gif)
```

