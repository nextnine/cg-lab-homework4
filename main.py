import taichi as ti

# 初始化 Taichi
ti.init(arch=ti.gpu)

# 窗口分辨率
res_x, res_y = 800, 600
pixels = ti.Vector.field(3, dtype=ti.f32, shape=(res_x, res_y))

# 定义全局交互参数
Ka = ti.field(ti.f32, shape=())
Kd = ti.field(ti.f32, shape=())
Ks = ti.field(ti.f32, shape=())
shininess = ti.field(ti.f32, shape=())

# 选做开关
use_blinn = ti.field(ti.i32, shape=())
enable_shadow = ti.field(ti.i32, shape=())


@ti.func
def normalize(v):
    return v / v.norm(1e-5)


@ti.func
def reflect(I, N):
    return I - 2.0 * I.dot(N) * N


@ti.func
def intersect_sphere(ro, rd, center, radius):
    t = -1.0
    normal = ti.Vector([0.0, 0.0, 0.0])

    oc = ro - center
    b = 2.0 * oc.dot(rd)
    c = oc.dot(oc) - radius * radius
    delta = b * b - 4.0 * c

    if delta > 0:
        sqrt_delta = ti.sqrt(delta)
        t1 = (-b - sqrt_delta) / 2.0
        t2 = (-b + sqrt_delta) / 2.0

        if t1 > 1e-4:
            t = t1
        elif t2 > 1e-4:
            t = t2

        if t > 0:
            p = ro + rd * t
            normal = normalize(p - center)

    return t, normal


@ti.func
def intersect_cone(ro, rd, apex, base_y, radius):
    """
    测试光线与竖直圆锥侧面相交
    apex: 圆锥顶点
    base_y: 底面高度
    radius: 底面半径
    """
    t = -1.0
    normal = ti.Vector([0.0, 0.0, 0.0])

    H = apex.y - base_y
    k = (radius / H) ** 2

    ro_local = ro - apex

    A = rd.x ** 2 + rd.z ** 2 - k * rd.y ** 2
    B = 2.0 * (
        ro_local.x * rd.x
        + ro_local.z * rd.z
        - k * ro_local.y * rd.y
    )
    C = ro_local.x ** 2 + ro_local.z ** 2 - k * ro_local.y ** 2

    if ti.abs(A) > 1e-5:
        delta = B ** 2 - 4.0 * A * C

        if delta > 0:
            sqrt_delta = ti.sqrt(delta)
            t1 = (-B - sqrt_delta) / (2.0 * A)
            t2 = (-B + sqrt_delta) / (2.0 * A)

            t_first = t1
            t_second = t2

            if t1 > t2:
                t_first, t_second = t_second, t_first

            y1 = ro_local.y + t_first * rd.y
            if t_first > 1e-4 and -H <= y1 <= 0:
                t = t_first
            else:
                y2 = ro_local.y + t_second * rd.y
                if t_second > 1e-4 and -H <= y2 <= 0:
                    t = t_second

            if t > 0:
                p_local = ro_local + rd * t

                normal = normalize(ti.Vector([
                    p_local.x,
                    -k * p_local.y,
                    p_local.z
                ]))

    return t, normal


@ti.func
def intersect_plane(ro, rd, y_pos):
    """
    地面平面求交：y = y_pos
    """
    t = -1.0
    normal = ti.Vector([0.0, 1.0, 0.0])

    if ti.abs(rd.y) > 1e-5:
        temp_t = (y_pos - ro.y) / rd.y

        if temp_t > 1e-4:
            t = temp_t

    return t, normal


@ti.func
def intersect_scene(ro, rd):
    """
    场景统一求交
    hit_id:
    0 = 未命中
    1 = 球体
    2 = 圆锥
    3 = 地面
    """
    min_t = 1e10
    hit_normal = ti.Vector([0.0, 0.0, 0.0])
    hit_color = ti.Vector([0.0, 0.0, 0.0])
    hit_id = 0

    # 红色球体
    t_sph, n_sph = intersect_sphere(
        ro,
        rd,
        ti.Vector([-1.2, -0.2, 0.0]),
        1.2
    )

    if 0 < t_sph < min_t:
        min_t = t_sph
        hit_normal = n_sph
        hit_color = ti.Vector([0.8, 0.1, 0.1])
        hit_id = 1

    # 紫色圆锥
    t_cone, n_cone = intersect_cone(
        ro,
        rd,
        ti.Vector([1.2, 1.2, 0.0]),
        -1.4,
        1.2
    )

    if 0 < t_cone < min_t:
        min_t = t_cone
        hit_normal = n_cone
        hit_color = ti.Vector([0.6, 0.2, 0.8])
        hit_id = 2

    # 新增：地面平面
    t_plane, n_plane = intersect_plane(ro, rd, -1.4)

    if 0 < t_plane < min_t:
        min_t = t_plane
        hit_normal = n_plane
        hit_color = ti.Vector([0.45, 0.45, 0.45])
        hit_id = 3

    return min_t, hit_normal, hit_color, hit_id


@ti.func
def in_shadow(p, N, light_pos):
    """
    硬阴影：
    从交点向光源发射 shadow ray。
    若在到达光源前碰到其他物体，则说明该点处于阴影中。
    """
    shadow = 0

    to_light = light_pos - p
    light_dist = to_light.norm(1e-5)
    shadow_dir = normalize(to_light)

    # 稍微偏移，避免自己遮挡自己
    shadow_origin = p + N * 1e-3

    t_shadow, _, _, _ = intersect_scene(shadow_origin, shadow_dir)

    if 0 < t_shadow < light_dist:
        shadow = 1

    return shadow


@ti.kernel
def render():
    for i, j in pixels:
        u = (i - res_x / 2.0) / res_y * 2.0
        v = (j - res_y / 2.0) / res_y * 2.0

        # 摄像机
        ro = ti.Vector([0.0, 0.0, 5.0])
        rd = normalize(ti.Vector([u, v, -1.0]))

        # 背景色
        color = ti.Vector([0.05, 0.15, 0.15])

        min_t, hit_normal, hit_color, hit_id = intersect_scene(ro, rd)

        if min_t < 1e9:
            p = ro + rd * min_t
            N = hit_normal

            # 地面棋盘格，让阴影更明显
            if hit_id == 3:
                checker = (ti.floor(p.x * 2.0) + ti.floor(p.z * 2.0)) % 2.0

                if checker < 0.5:
                    hit_color = ti.Vector([0.38, 0.38, 0.38])
                else:
                    hit_color = ti.Vector([0.58, 0.58, 0.58])

            # 光源
            light_pos = ti.Vector([2.0, 3.0, 4.0])
            light_color = ti.Vector([1.0, 1.0, 1.0])

            L = normalize(light_pos - p)
            V = normalize(ro - p)

            # Ambient
            ambient = Ka[None] * light_color * hit_color

            # Diffuse
            diff = ti.max(0.0, N.dot(L))
            diffuse = Kd[None] * diff * light_color * hit_color

            # Specular
            spec = 0.0

            if use_blinn[None] == 1:
                # Blinn-Phong：使用半程向量 H
                H = normalize(L + V)
                spec = ti.max(0.0, N.dot(H)) ** shininess[None]
            else:
                # Phong：使用反射向量 R
                R = normalize(reflect(-L, N))
                spec = ti.max(0.0, R.dot(V)) ** shininess[None]

            specular = Ks[None] * spec * light_color

            if enable_shadow[None] == 1:
                shadow = in_shadow(p, N, light_pos)

                if shadow == 1:
                    # 阴影区域只保留环境光
                    color = ambient
                else:
                    color = ambient + diffuse + specular
            else:
                color = ambient + diffuse + specular

        pixels[i, j] = ti.math.clamp(color, 0.0, 1.0)


def main():
    window = ti.ui.Window("Phong / Blinn-Phong With Hard Shadow", (res_x, res_y))
    canvas = window.get_canvas()
    gui = window.get_gui()

    # 默认参数不要全部设为 1，否则会过曝发白
    Ka[None] = 0.2
    Kd[None] = 0.7
    Ks[None] = 0.5
    shininess[None] = 32.0

    use_blinn[None] = 1
    enable_shadow[None] = 1

    while window.running:
        render()

        canvas.set_image(pixels)

        with gui.sub_window("Material Parameters", 0.66, 0.05, 0.32, 0.32):
            Ka[None] = gui.slider_float("Ka Ambient", Ka[None], 0.0, 1.0)
            Kd[None] = gui.slider_float("Kd Diffuse", Kd[None], 0.0, 1.0)
            Ks[None] = gui.slider_float("Ks Specular", Ks[None], 0.0, 1.0)
            shininess[None] = gui.slider_float("Shininess", shininess[None], 1.0, 128.0)

            blinn_bool = use_blinn[None] == 1
            shadow_bool = enable_shadow[None] == 1

            blinn_bool = gui.checkbox("Use Blinn-Phong", blinn_bool)
            shadow_bool = gui.checkbox("Enable Hard Shadow", shadow_bool)

            use_blinn[None] = 1 if blinn_bool else 0
            enable_shadow[None] = 1 if shadow_bool else 0

        window.show()


if __name__ == "__main__":
    main()