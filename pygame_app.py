"""
Physics Animator - Pygame frontend
Connects to the FastAPI backend (/generate) and renders the
returned animation with a draggable time scrubber.

Run:
    pip install pygame requests
    python pygame_app.py
"""

import pygame
import requests
import sys
import textwrap

API_URL = "http://localhost:8000/generate"

WIDTH, HEIGHT = 600, 560          # extra space below canvas for UI
CANVAS_H = 400
FPS = 60

WHITE   = (255, 255, 255)
BLACK   = (20, 20, 30)
GRAY    = (90, 90, 110)
PURPLE  = (167, 139, 250)
BLUE    = (96, 165, 250)
GREEN   = (110, 231, 183)
PANEL   = (19, 19, 43)
RED     = (248, 113, 113)


def lerp(a, b, t):
    return a + (b - a) * t


def ease_in_out(t):
    return 2 * t * t if t < 0.5 else 1 - (-2 * t + 2) ** 2 / 2


def get_prop(keyframes, t, prop, default=0):
    kfs = sorted(keyframes, key=lambda k: k["t"])
    if t <= kfs[0]["t"]:
        return kfs[0].get(prop, default)
    if t >= kfs[-1]["t"]:
        return kfs[-1].get(prop, default)
    for a, b in zip(kfs, kfs[1:]):
        if a["t"] <= t <= b["t"]:
            span = b["t"] - a["t"]
            alpha = 0 if span == 0 else (t - a["t"]) / span
            alpha = ease_in_out(alpha)
            va = a.get(prop, default)
            vb = b.get(prop, default)
            return lerp(va, vb, alpha)
    return default


def hex_to_rgb(h):
    h = h.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    try:
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    except Exception:
        return (100, 150, 200)


def draw_object(surface, obj, t):
    x = get_prop(obj["keyframes"], t, "x", 300)
    y = get_prop(obj["keyframes"], t, "y", 200)
    rotation = get_prop(obj["keyframes"], t, "rotation", 0)
    opacity = get_prop(obj["keyframes"], t, "opacity", 1)
    scale_x = get_prop(obj["keyframes"], t, "scaleX", 1)
    scale_y = get_prop(obj["keyframes"], t, "scaleY", 1)

    w = obj.get("width", 30) * scale_x
    h = obj.get("height", 30) * scale_y
    color = hex_to_rgb(obj.get("color", "#4a90d9"))
    shape = obj.get("shape", "rect")

    alpha = max(0, min(255, int(opacity * 255)))

    # Render onto a small transparent surface so we can rotate + alpha
    pad = int(max(w, h) * 1.6) + 4
    obj_surf = pygame.Surface((pad, pad), pygame.SRCALPHA)
    cx, cy = pad // 2, pad // 2

    if shape == "circle":
        r = int(w / 2)
        pygame.draw.circle(obj_surf, (*color, alpha), (cx, cy), r)
        pygame.draw.circle(obj_surf, (0, 0, 0, 40), (cx, cy), r, 2)
        # shine
        shine_pos = (int(cx - r * 0.3), int(cy - r * 0.3))
        pygame.draw.circle(obj_surf, (255, 255, 255, 90), shine_pos, max(2, int(r * 0.25)))
    elif shape == "rect":
        rect = pygame.Rect(0, 0, int(w), int(h))
        rect.center = (cx, cy)
        pygame.draw.rect(obj_surf, (*color, alpha), rect, border_radius=3)
        pygame.draw.rect(obj_surf, (0, 0, 0, 40), rect, 2, border_radius=3)
    elif shape == "triangle":
        pts = [(cx, cy - h / 2), (cx + w / 2, cy + h / 2), (cx - w / 2, cy + h / 2)]
        pygame.draw.polygon(obj_surf, (*color, alpha), pts)
        pygame.draw.polygon(obj_surf, (0, 0, 0, 40), pts, 2)
    elif shape == "line":
        thickness = max(2, int(h))
        pygame.draw.line(obj_surf, (*color, alpha), (cx - w / 2, cy), (cx + w / 2, cy), thickness)

    # rotate
    rotated = pygame.transform.rotate(obj_surf, -rotation)
    rect = rotated.get_rect(center=(int(x), int(y)))
    surface.blit(rotated, rect)

    # label
    label = obj.get("label", "")
    if label and shape != "line":
        font = pygame.font.SysFont("couriernew", 12, bold=True)
        text = font.render(label, True, (60, 60, 70))
        text_rect = text.get_rect(center=(int(x), int(y + h / 2 + 12)))
        surface.blit(text, text_rect)


def draw_button(surface, rect, text, font, bg, fg=WHITE):
    pygame.draw.rect(surface, bg, rect, border_radius=8)
    label = font.render(text, True, fg)
    surface.blit(label, label.get_rect(center=rect.center))


def wrap_text(text, font, max_width):
    words = text.split(" ")
    lines, current = [], ""
    for w in words:
        test = (current + " " + w).strip()
        if font.size(test)[0] <= max_width:
            current = test
        else:
            lines.append(current)
            current = w
    if current:
        lines.append(current)
    return lines


def get_current_explanation(explanations, t):
    sorted_exps = sorted(explanations, key=lambda e: e["t"])
    best = sorted_exps[0]
    for e in sorted_exps:
        if e["t"] <= t:
            best = e
    return best


def fetch_animation(description):
    res = requests.post(API_URL, json={"description": description}, timeout=120)
    res.raise_for_status()
    return res.json()


def main():
    pygame.init()

    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("Physics Animator")
    clock = pygame.time.Clock()

    font_title = pygame.font.SysFont("couriernew", 22, bold=True)
    font_small = pygame.font.SysFont("couriernew", 13)
    font_tiny = pygame.font.SysFont("couriernew", 11)
    font_input = pygame.font.SysFont("arial", 16)

    # State
    input_text = "A ball rolls off a table and bounces twice"
    input_active = True
    anim_data = None
    current_t = 0.0
    playing = False
    loading = False
    error_msg = ""

    scrubber_rect = pygame.Rect(20, CANVAS_H + 90, WIDTH - 40, 6)
    play_btn = pygame.Rect(20, CANVAS_H + 110, 90, 32)
    reset_btn = pygame.Rect(120, CANVAS_H + 110, 90, 32)
    generate_btn = pygame.Rect(WIDTH - 120, 20, 100, 32)
    input_box = pygame.Rect(20, 20, WIDTH - 150, 32)

    dragging_scrubber = False

    def do_generate():
        nonlocal anim_data, current_t, playing, loading, error_msg
        if not input_text.strip():
            return
        loading = True
        error_msg = ""
        pygame.display.set_caption("Physics Animator - Generating...")
        screen_redraw()  # show loading state immediately
        try:
            anim_data = fetch_animation(input_text.strip())
            current_t = 0.0
            playing = False
        except Exception as e:
            error_msg = f"Error: {e}"
            anim_data = None
        loading = False
        pygame.display.set_caption("Physics Animator")

    def screen_redraw():
        screen.fill(BLACK)
        pygame.display.flip()

    running = True
    while running:
        dt = clock.tick(FPS) / 1000.0

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            elif event.type == pygame.KEYDOWN:
                if input_active:
                    if event.key == pygame.K_RETURN:
                        do_generate()
                    elif event.key == pygame.K_BACKSPACE:
                        input_text = input_text[:-1]
                    elif event.key == pygame.K_ESCAPE:
                        input_active = False
                    else:
                        if len(input_text) < 120:
                            input_text += event.unicode

            elif event.type == pygame.MOUSEBUTTONDOWN:
                mx, my = event.pos

                if input_box.collidepoint(mx, my):
                    input_active = True
                else:
                    input_active = False

                if generate_btn.collidepoint(mx, my):
                    do_generate()

                if anim_data:
                    if play_btn.collidepoint(mx, my):
                        if current_t >= anim_data["duration"]:
                            current_t = 0
                        playing = not playing

                    if reset_btn.collidepoint(mx, my):
                        playing = False
                        current_t = 0

                    if scrubber_rect.collidepoint(mx, my):
                        dragging_scrubber = True
                        playing = False
                        rel = (mx - scrubber_rect.x) / scrubber_rect.width
                        current_t = max(0, min(1, rel)) * anim_data["duration"]

            elif event.type == pygame.MOUSEBUTTONUP:
                dragging_scrubber = False

            elif event.type == pygame.MOUSEMOTION:
                if dragging_scrubber and anim_data:
                    mx, _ = event.pos
                    rel = (mx - scrubber_rect.x) / scrubber_rect.width
                    current_t = max(0, min(1, rel)) * anim_data["duration"]

        # Update animation time
        if anim_data and playing:
            current_t += dt
            if current_t >= anim_data["duration"]:
                current_t = anim_data["duration"]
                playing = False

        # ── DRAW ──────────────────────────────────────────
        screen.fill(BLACK)

        # Input box
        pygame.draw.rect(screen, (30, 30, 55), input_box, border_radius=6)
        pygame.draw.rect(screen, PURPLE if input_active else GRAY, input_box, 2, border_radius=6)
        txt_surf = font_input.render(input_text, True, WHITE)
        screen.blit(txt_surf, (input_box.x + 8, input_box.y + 6))

        # Generate button
        gen_color = GRAY if loading else PURPLE
        draw_button(screen, generate_btn, "..." if loading else "Generate", font_small, gen_color)

        if error_msg:
            err_lines = wrap_text(error_msg, font_tiny, WIDTH - 40)
            for i, line in enumerate(err_lines[:3]):
                err_surf = font_tiny.render(line, True, RED)
                screen.blit(err_surf, (20, 60 + i * 16))

        canvas_top = 110

        if anim_data:
            # Canvas background
            bg_color = hex_to_rgb(anim_data.get("background", "#e8f0f8"))
            canvas_rect = pygame.Rect(0, canvas_top, WIDTH, CANVAS_H)
            pygame.draw.rect(screen, bg_color, canvas_rect)

            # grid
            for gx in range(0, WIDTH, 40):
                pygame.draw.line(screen, (0, 0, 0, 10), (gx, canvas_top), (gx, canvas_top + CANVAS_H))
            for gy in range(canvas_top, canvas_top + CANVAS_H, 40):
                pygame.draw.line(screen, (0, 0, 0, 10), (0, gy), (WIDTH, gy))

            # objects (translate y by canvas_top)
            sub = screen.subsurface(canvas_rect)
            for obj in anim_data["objects"]:
                draw_object(sub, obj, current_t)

            pygame.draw.rect(screen, PURPLE, canvas_rect, 2)

            # Title
            title_surf = font_title.render(anim_data.get("title", ""), True, PURPLE)
            screen.blit(title_surf, (20, canvas_top + CANVAS_H + 8))

            dur_surf = font_tiny.render(f"t = {current_t:.2f}s / {anim_data['duration']}s", True, GRAY)
            screen.blit(dur_surf, (WIDTH - dur_surf.get_width() - 20, canvas_top + CANVAS_H + 12))

            # Explanation
            exp = get_current_explanation(anim_data["explanations"], current_t)
            exp_lines = wrap_text("● " + exp["text"], font_small, WIDTH - 40)
            for i, line in enumerate(exp_lines[:2]):
                exp_surf = font_small.render(line, True, BLUE)
                screen.blit(exp_surf, (20, canvas_top + CANVAS_H + 36 + i * 18))

            # Scrubber
            pygame.draw.rect(screen, (60, 60, 80), scrubber_rect, border_radius=3)
            progress = current_t / anim_data["duration"] if anim_data["duration"] else 0
            fill_rect = pygame.Rect(scrubber_rect.x, scrubber_rect.y,
                                     int(scrubber_rect.width * progress), scrubber_rect.height)
            pygame.draw.rect(screen, PURPLE, fill_rect, border_radius=3)

            # Handle
            handle_x = scrubber_rect.x + int(scrubber_rect.width * progress)
            pygame.draw.circle(screen, WHITE, (handle_x, scrubber_rect.y + 3), 7)
            pygame.draw.circle(screen, PURPLE, (handle_x, scrubber_rect.y + 3), 7, 2)

            # Explanation markers
            for ex in anim_data["explanations"]:
                mx = scrubber_rect.x + int(scrubber_rect.width * (ex["t"] / anim_data["duration"]))
                pygame.draw.circle(screen, GREEN, (mx, scrubber_rect.y + 3), 3)

            # Buttons
            draw_button(screen, play_btn, "Pause" if playing else "Play", font_small, BLUE)
            draw_button(screen, reset_btn, "Reset", font_small, (60, 60, 80))

            # Physics summary
            sum_lines = wrap_text(anim_data.get("physics_summary", ""), font_tiny, WIDTH - 40)
            for i, line in enumerate(sum_lines[:3]):
                s_surf = font_tiny.render(line, True, GREEN)
                screen.blit(s_surf, (20, CANVAS_H + 152 + i * 15))

            provider = anim_data.get("_provider", "")
            if provider:
                p_surf = font_tiny.render(f"via {provider}", True, GRAY)
                screen.blit(p_surf, (WIDTH - p_surf.get_width() - 10, HEIGHT - 18))

        else:
            # Empty state
            pygame.draw.rect(screen, (15, 15, 30), pygame.Rect(0, canvas_top, WIDTH, CANVAS_H))
            msg = "Type a description above and click Generate"
            msg_surf = font_small.render(msg, True, GRAY)
            screen.blit(msg_surf, msg_surf.get_rect(center=(WIDTH // 2, canvas_top + CANVAS_H // 2)))

        pygame.display.flip()

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()
