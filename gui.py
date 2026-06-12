"""
Physics Animator — Pygame Frontend
A clean, "explainer video" style UI (whiteboard / educational theme).

Starts apis.py in a background thread automatically.
Run:
    python gui.py
"""

import threading
import sys
import time
import math

import pygame
import requests

import apis  # apis.py (FastAPI + Groq/Gemini)

API_URL = "http://127.0.0.1:8000/generate"

# ─── Layout Defaults ────────────────────────────────────────────────────────
WIDTH, HEIGHT = 760, 760
FPS = 60

# ─── Light Educational Theme ────────────────────────────────────────────────
BG          = (248, 249, 250)   # Light off-white (whiteboard)
PANEL       = (255, 255, 255)   # White panels
BORDER      = (226, 232, 240)   # Light gray border
TEXT_MAIN   = (30, 41, 59)      # Slate 800
TEXT_MUTED  = (100, 116, 139)   # Slate 500
ACCENT      = (59, 130, 246)    # Blue 500
ACCENT_HOVER= (37, 99, 235)     # Blue 600
ACCENT3     = (16, 185, 129)    # Emerald 500
ERROR       = (239, 68, 68)     # Red 500
WHITE       = (255, 255, 255)


# ─── Animation math helpers ───────────────────────────────────────────────────

def lerp(a, b, t):
    return a + (b - a) * t


def ease_in_out(t):
    return 2 * t * t if t < 0.5 else 1 - (-2 * t + 2) ** 2 / 2


def get_prop(keyframes, t, prop, default=0):
    if not keyframes: return default
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
            return lerp(a.get(prop, default), b.get(prop, default), alpha)
    return default


def hex_to_rgb(h):
    h = h.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    try:
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    except Exception:
        return (59, 130, 246) # default accent blue


def with_alpha(color, alpha):
    return (color[0], color[1], color[2], alpha)


# ─── Drawing primitives ────────────────────────────────────────────────────────

def draw_object(surface, obj, t, trail_points=None):
    x = get_prop(obj.get("keyframes", []), t, "x", 300)
    y = get_prop(obj.get("keyframes", []), t, "y", 200)
    rotation = get_prop(obj.get("keyframes", []), t, "rotation", 0)
    opacity = get_prop(obj.get("keyframes", []), t, "opacity", 1)
    scale_x = get_prop(obj.get("keyframes", []), t, "scaleX", 1)
    scale_y = get_prop(obj.get("keyframes", []), t, "scaleY", 1)

    w = obj.get("width", 30) * scale_x
    h = obj.get("height", 30) * scale_y
    color = hex_to_rgb(obj.get("color", "#3b82f6"))
    shape = obj.get("shape", "rect")
    alpha = max(0, min(255, int(opacity * 255)))

    pad = int(max(w, h) * 1.7) + 6
    obj_surf = pygame.Surface((pad, pad), pygame.SRCALPHA)
    cx, cy = pad // 2, pad // 2

    if shape == "circle":
        r = int(w / 2)
        pygame.draw.circle(obj_surf, (*color, alpha), (cx, cy), r)
        pygame.draw.circle(obj_surf, (255, 255, 255, 80), (cx, cy), r, 2)
    elif shape == "rect":
        rect = pygame.Rect(0, 0, int(w), int(h)); rect.center = (cx, cy)
        pygame.draw.rect(obj_surf, (*color, alpha), rect, border_radius=4)
        pygame.draw.rect(obj_surf, (255, 255, 255, 80), rect, 2, border_radius=4)
    elif shape == "triangle":
        pts = [(cx, cy - h / 2), (cx + w / 2, cy + h / 2), (cx - w / 2, cy + h / 2)]
        pygame.draw.polygon(obj_surf, (*color, alpha), pts)
        pygame.draw.polygon(obj_surf, (255, 255, 255, 80), pts, 2)
    elif shape == "line":
        thickness = max(2, int(h))
        pygame.draw.line(obj_surf, (*color, alpha), (cx - w / 2, cy), (cx + w / 2, cy), thickness)

    rotated = pygame.transform.rotate(obj_surf, -rotation)
    rect = rotated.get_rect(center=(int(x), int(y)))
    surface.blit(rotated, rect)

    label = obj.get("label", "")
    if label and shape != "line":
        font = pygame.font.SysFont("segoeui,arial", 13, bold=True)
        text = font.render(label, True, TEXT_MAIN)
        shadow = font.render(label, True, WHITE)
        pos = text.get_rect(center=(int(x), int(y + h / 2 + 14)))
        # Outline for readability
        for dx, dy in [(-1,-1), (1,-1), (-1,1), (1,1), (0,-1), (-1,0), (1,0), (0,1)]:
            surface.blit(shadow, (pos.x + dx, pos.y + dy))
        surface.blit(text, pos)

def draw_vectors(surface, obj, t):
    vectors = obj.get("vectors", [])
    if not vectors: return
    
    v_by_type = {}
    for v in vectors:
        v_by_type.setdefault(v.get("type", "velocity"), []).append(v)
        
    for v_type, vecs in v_by_type.items():
        vecs.sort(key=lambda k: k["t"])
        if len(vecs) == 1:
            v = vecs[0]
            dt = abs(t - v["t"])
            if dt > 0.5: continue
            alpha = max(0, 1.0 - (dt / 0.5))
            v_dx, v_dy, v_mag = v.get("dx", 0), v.get("dy", 0), v.get("magnitude", 0) * alpha
            v_x, v_y = v.get("x", 0), v.get("y", 0)
        else:
            if t < vecs[0]["t"] - 0.5 or t > vecs[-1]["t"] + 0.5:
                continue
            
            v_dx = get_prop(vecs, t, "dx", 0)
            v_dy = get_prop(vecs, t, "dy", 0)
            v_mag = get_prop(vecs, t, "magnitude", 0)
            v_x = get_prop(vecs, t, "x", 0)
            v_y = get_prop(vecs, t, "y", 0)
            
            if t < vecs[0]["t"]:
                v_mag *= max(0, 1.0 - (vecs[0]["t"] - t) / 0.5)
            elif t > vecs[-1]["t"]:
                v_mag *= max(0, 1.0 - (t - vecs[-1]["t"]) / 0.5)

        if v_mag < 0.5: continue
        
        if v_type == "velocity": color = (59, 130, 246)
        elif v_type == "acceleration": color = (16, 185, 129)
        elif v_type == "force": color = (239, 68, 68)
        else: color = (100, 100, 100)
        
        length = v_mag * 3 
        dist = math.hypot(v_dx, v_dy)
        if dist > 0.001:
            nx, ny = v_dx / dist, v_dy / dist
        else:
            nx, ny = 1, 0
            
        end_x = v_x + nx * length
        end_y = v_y + ny * length
        
        pygame.draw.line(surface, color, (v_x, v_y), (end_x, end_y), 3)
        head_len = 8
        angle = math.atan2(ny, nx)
        p1 = (end_x - head_len * math.cos(angle - math.pi/6), end_y - head_len * math.sin(angle - math.pi/6))
        p2 = (end_x - head_len * math.cos(angle + math.pi/6), end_y - head_len * math.sin(angle + math.pi/6))
        pygame.draw.polygon(surface, color, [(end_x, end_y), p1, p2])

def rounded_rect(surface, rect, color, radius=10, width=0):
    pygame.draw.rect(surface, color, rect, width, border_radius=radius)


def draw_shadow(surface, rect, radius=10, offset=(0, 4), alpha=30):
    shadow_surf = pygame.Surface((rect.width + 20, rect.height + 20), pygame.SRCALPHA)
    for i in range(4):
        a = alpha - i * 6
        if a > 0:
            r = pygame.Rect(10 - i, 10 - i + offset[1], rect.width + i*2, rect.height + i*2)
            rounded_rect(shadow_surf, r, (0, 0, 0, a), radius=radius+i)
    surface.blit(shadow_surf, (rect.x - 10, rect.y - 10))


def wrap_text(text, font, max_width):
    words = text.split(" ")
    lines, current = [], ""
    for w in words:
        test = (current + " " + w).strip()
        if font.size(test)[0] <= max_width:
            current = test
        else:
            lines.append(current); current = w
    if current:
        lines.append(current)
    return lines


def get_current_explanation(explanations, t):
    sorted_exps = sorted(explanations, key=lambda e: e["t"])
    if not sorted_exps:
        return {"text": ""}
    best = sorted_exps[0]
    for e in sorted_exps:
        if e["t"] <= t:
            best = e
    return best


def fetch_animation(description):
    res = requests.post(API_URL, json={"description": description}, timeout=120)
    res.raise_for_status()
    return res.json()


# ─── Main app ──────────────────────────────────────────────────────────────────

class App:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.RESIZABLE)
        pygame.display.set_caption("Physics Animator")
        self.clock = pygame.time.Clock()

        self.font_title  = pygame.font.SysFont("segoeui,arial", 24, bold=True)
        self.font_body   = pygame.font.SysFont("segoeui,arial", 15)
        self.font_small  = pygame.font.SysFont("segoeui,arial", 13)
        self.font_tiny   = pygame.font.SysFont("segoeui,arial", 11, bold=True)
        self.font_mono   = pygame.font.SysFont("consolas,monospace", 12)

        self.input_text = ""
        self.placeholder = "Ask a physics question… e.g. 'a ball rolls off a table and bounces'"
        self.input_active = True
        self.cursor_visible = True
        self.cursor_timer = 0.0

        self.anim_data = None
        self.current_t = 0.0
        self.playing = False
        self.loading = False
        self.loading_dots = 0
        self.loading_timer = 0.0
        self.error_msg = ""
        self.mouse_pos = (0, 0)
        self.show_summary = False

        # trail history: obj_id -> list of (x, y)
        self.trails = {}
        self.last_trail_t = -1

        self._update_layout(self.screen.get_width(), self.screen.get_height())

    # ── layout rects ──────────────────────────────────────────────────────
    def _update_layout(self, w, h):
        self.width = w
        self.height = h
        
        self.canvas_rect = pygame.Rect(0, 0, self.width, self.height)
        
        box_w = min(600, self.width - 40)
        self.input_box = pygame.Rect((self.width - box_w) // 2, self.height - 70, box_w, 50)
        self.send_btn = pygame.Rect(self.input_box.right - 46, self.input_box.top + 5, 40, 40)
        
        ctrl_w = 400
        self.controls_rect = pygame.Rect((self.width - ctrl_w) // 2, self.input_box.top - 60, ctrl_w, 40)
        self.play_btn = pygame.Rect(self.controls_rect.x + 10, self.controls_rect.y + 5, 30, 30)
        self.scrubber_rect = pygame.Rect(self.play_btn.right + 15, self.controls_rect.y + 16, ctrl_w - 65, 8)
        
        self.explain_rect = pygame.Rect((self.width - 600) // 2, self.controls_rect.top - 60, 600, 50)
        
        self.summary_toggle_btn = pygame.Rect(self.width - 50, 20, 30, 30)
        self.summary_rect = pygame.Rect(self.width - 320, 60, 300, 200)

    # ── networking ────────────────────────────────────────────────────────
    def do_generate(self):
        text = self.input_text.strip()
        if not text or self.loading:
            return
        self.loading = True
        self.error_msg = ""

        def worker():
            try:
                data = fetch_animation(text)
                self.anim_data = data
                self.current_t = 0.0
                self.playing = False
                self.trails = {}
                self.show_summary = False
            except Exception as e:
                self.error_msg = f"Error: {e}"
                self.anim_data = None
                self.show_summary = True
            finally:
                self.loading = False

        threading.Thread(target=worker, daemon=True).start()
        self.input_text = ""

    # ── drawing ───────────────────────────────────────────────────────────
    def draw_canvas(self):
        pygame.draw.rect(self.screen, BG, self.canvas_rect)

        # Whiteboard faint grid
        grid_col = (235, 240, 245)
        for gx in range(0, self.width, 40):
            pygame.draw.line(self.screen, grid_col, (gx, 0), (gx, self.canvas_rect.bottom), 1)
        for gy in range(0, self.canvas_rect.bottom, 40):
            pygame.draw.line(self.screen, grid_col, (0, gy), (self.width, gy), 1)

        if self.anim_data:
            sub = self.screen.subsurface(self.canvas_rect)
            
            # preserve aspect ratio (600x400 from apis)
            aspect = 600 / 400
            if self.canvas_rect.height > 0:
                rect_aspect = self.canvas_rect.width / self.canvas_rect.height
                if rect_aspect > aspect:
                    draw_h = self.canvas_rect.height
                    draw_w = draw_h * aspect
                else:
                    draw_w = self.canvas_rect.width
                    draw_h = draw_w / aspect
            else:
                draw_w, draw_h = 0, 0
                
            draw_x = (self.canvas_rect.width - draw_w) / 2
            draw_y = (self.canvas_rect.height - draw_h) / 2

            # update trails (sample positions over time)
            for obj in self.anim_data["objects"]:
                oid = obj["id"]
                x = get_prop(obj.get("keyframes", []), self.current_t, "x", 300)
                y = get_prop(obj.get("keyframes", []), self.current_t, "y", 200)
                
                screen_x = draw_x + x * (draw_w / 600)
                screen_y = draw_y + y * (draw_h / 400)
                
                trail = self.trails.setdefault(oid, [])
                if not trail or (abs(trail[-1][0] - screen_x) > 1 or abs(trail[-1][1] - screen_y) > 1):
                    trail.append((screen_x, screen_y))
                    if len(trail) > 18:
                        trail.pop(0)
                if self.current_t < self.last_trail_t - 0.001:
                    self.trails[oid] = []
            self.last_trail_t = self.current_t

            # draw scaled objects & vectors
            if draw_w > 0 and draw_h > 0:
                base = pygame.Surface((600, 400), pygame.SRCALPHA)
                for obj in self.anim_data["objects"]:
                    draw_object(base, obj, self.current_t)
                for obj in self.anim_data["objects"]:
                    draw_vectors(base, obj, self.current_t)
                    
                scaled = pygame.transform.smoothscale(base, (int(draw_w), int(draw_h)))
                sub.blit(scaled, (int(draw_x), int(draw_y)))

            # trails drawn directly at screen scale (after objects, subtly)
            for oid, pts in self.trails.items():
                obj = next((o for o in self.anim_data["objects"] if o["id"] == oid), None)
                if obj and obj.get("shape") == "circle" and len(pts) > 1:
                    color = hex_to_rgb(obj.get("color", "#3b82f6"))
                    for i, (px, py) in enumerate(pts[:-1]):
                        fade = int(90 * (i + 1) / len(pts))
                        pygame.draw.circle(sub, with_alpha(color, fade), (int(px), int(py)), 3)

            # title overlay top-left
            title = self.anim_data.get("title", "")
            if title:
                title_surf = self.font_title.render(title, True, TEXT_MAIN)
                pad = 12
                bg_rect = pygame.Rect(16, 16, title_surf.get_width() + pad*2, title_surf.get_height() + 8)
                rounded_rect(sub, bg_rect, (255, 255, 255, 210), radius=12)
                sub.blit(title_surf, (16 + pad, 20))

            # time badge top-right
            dur = self.anim_data.get("duration", 1)
            t_text = f"t = {self.current_t:0.2f}s / {dur:0.1f}s"
            t_surf = self.font_mono.render(t_text, True, TEXT_MAIN)
            t_bg = pygame.Surface((t_surf.get_width() + 16, t_surf.get_height() + 10), pygame.SRCALPHA)
            rounded_rect(t_bg, t_bg.get_rect(), (255, 255, 255, 210), radius=8)
            t_bg.blit(t_surf, (8, 5))
            # offset from toggle button
            sub.blit(t_bg, (self.canvas_rect.width - t_bg.get_width() - 60, 20))

        else:
            # Empty / welcome state
            big = self.font_title.render("Physics Animator", True, ACCENT)
            self.screen.blit(big, big.get_rect(center=(self.canvas_rect.width // 2, self.canvas_rect.height // 2 - 30)))
            sub_text = self.font_body.render("Describe an event below — watch it play out, scrub through time.", True, TEXT_MUTED)
            self.screen.blit(sub_text, sub_text.get_rect(center=(self.canvas_rect.width // 2, self.canvas_rect.height // 2 + 10)))

            if self.loading:
                dots = "." * (1 + self.loading_dots % 3)
                load_surf = self.font_body.render(f"Generating animation{dots}", True, ACCENT)
                self.screen.blit(load_surf, load_surf.get_rect(center=(self.canvas_rect.width // 2, self.canvas_rect.height // 2 + 45)))

        # loading shimmer bar at top
        if self.loading and self.anim_data:
            bar_w = self.width * (0.3 + 0.7 * (0.5 + 0.5 * math.sin(self.loading_timer * 4)))
            pygame.draw.rect(self.screen, ACCENT, (0, 0, int(bar_w), 4))

    def draw_explanation(self):
        if not self.anim_data: return
        exp = get_current_explanation(self.anim_data.get("explanations", []), self.current_t)
        text = exp.get("text", "")
        formula = exp.get("formula", "")
        if not text and not formula: return
        
        # Draw floating subtitle overlay
        lines = wrap_text(text, self.font_body, 560)
        total_h = len(lines) * 20 + (25 if formula else 0) + 20
        bg_rect = pygame.Rect(0, 0, 580, total_h)
        bg_rect.center = (self.width // 2, self.controls_rect.top - 20 - total_h // 2)
        
        rounded_rect(self.screen, bg_rect, (0, 0, 0, 160), radius=12) # Dark semi-transparent
        
        start_y = bg_rect.top + 10
        for i, line in enumerate(lines[:2]):
            surf = self.font_body.render(line, True, WHITE)
            self.screen.blit(surf, surf.get_rect(center=(self.width // 2, start_y + i * 20 + 10)))
            
        if formula:
            formula_surf = self.font_title.render(f"{formula}", True, (255, 215, 0)) # Gold formula
            self.screen.blit(formula_surf, formula_surf.get_rect(center=(self.width // 2, bg_rect.bottom - 18)))

    def draw_controls(self):
        if not self.anim_data: return
        duration = self.anim_data.get("duration", 1)

        draw_shadow(self.screen, self.controls_rect, radius=20, alpha=20)
        rounded_rect(self.screen, self.controls_rect, PANEL, radius=20)
        rounded_rect(self.screen, self.controls_rect, BORDER, radius=20, width=1)
        
        # Play/Pause button
        hovering_play = self.play_btn.collidepoint(self.mouse_pos)
        color = ACCENT_HOVER if hovering_play else ACCENT
        rounded_rect(self.screen, self.play_btn, color, radius=15)
        
        cx, cy = self.play_btn.center
        if self.playing:
            pygame.draw.rect(self.screen, WHITE, (cx - 4, cy - 5, 3, 10), border_radius=1)
            pygame.draw.rect(self.screen, WHITE, (cx + 2, cy - 5, 3, 10), border_radius=1)
        else:
            pygame.draw.polygon(self.screen, WHITE, [(cx - 3, cy - 5), (cx - 3, cy + 5), (cx + 5, cy)])

        # Scrubber track
        rounded_rect(self.screen, self.scrubber_rect, (226, 232, 240), radius=4)
        progress = (self.current_t / duration) if duration else 0
        fill_w = int(self.scrubber_rect.width * progress)
        if fill_w > 0:
            fill = pygame.Rect(self.scrubber_rect.x, self.scrubber_rect.y, fill_w, self.scrubber_rect.height)
            rounded_rect(self.screen, fill, ACCENT, radius=4)

        # explanation markers
        for ex in self.anim_data.get("explanations", []):
            mx = self.scrubber_rect.x + int(self.scrubber_rect.width * (ex["t"] / duration))
            pygame.draw.circle(self.screen, (255, 215, 0) if ex.get("formula") else ACCENT3, (mx, self.scrubber_rect.centery), 4)

        # handle
        handle_x = self.scrubber_rect.x + fill_w
        pygame.draw.circle(self.screen, WHITE, (handle_x, self.scrubber_rect.centery), 6)
        pygame.draw.circle(self.screen, ACCENT, (handle_x, self.scrubber_rect.centery), 6, 2)
        
        # hover on scrubber
        expanded = self.scrubber_rect.inflate(0, 16)
        if expanded.collidepoint(self.mouse_pos):
            pygame.draw.circle(self.screen, ACCENT, (handle_x, self.scrubber_rect.centery), 10, 1)

    def draw_summary(self):
        if not self.anim_data and not self.error_msg: return
        
        # Draw toggle button
        hovering_toggle = self.summary_toggle_btn.collidepoint(self.mouse_pos)
        toggle_col = PANEL if hovering_toggle else (240, 240, 240)
        rounded_rect(self.screen, self.summary_toggle_btn, toggle_col, radius=15)
        rounded_rect(self.screen, self.summary_toggle_btn, BORDER, radius=15, width=1)
        icon_text = "-" if self.show_summary else "i"
        icon_surf = self.font_body.render(icon_text, True, TEXT_MAIN)
        self.screen.blit(icon_surf, icon_surf.get_rect(center=self.summary_toggle_btn.center))

        if not self.show_summary: return

        card_rect = self.summary_rect
        draw_shadow(self.screen, card_rect, radius=8, alpha=15)
        rounded_rect(self.screen, card_rect, PANEL, radius=8)
        rounded_rect(self.screen, card_rect, BORDER, radius=8, width=1)

        if self.anim_data and self.anim_data.get("physics_summary"):
            label = self.font_tiny.render("KEY CONCEPTS", True, ACCENT)
            self.screen.blit(label, (card_rect.x + 16, card_rect.y + 10))
            
            lines = []
            for block in self.anim_data["physics_summary"].split('\n'):
                lines.extend(wrap_text(block, self.font_body, card_rect.width - 32))
            for i, line in enumerate(lines[:8]):
                surf = self.font_body.render(line, True, TEXT_MAIN)
                self.screen.blit(surf, (card_rect.x + 16, card_rect.y + 30 + i * 20))
        elif self.error_msg:
            label = self.font_tiny.render("ERROR", True, ERROR)
            self.screen.blit(label, (card_rect.x + 16, card_rect.y + 10))
            for i, line in enumerate(wrap_text(self.error_msg, self.font_body, card_rect.width - 32)[:4]):
                surf = self.font_body.render(line, True, ERROR)
                self.screen.blit(surf, (card_rect.x + 16, card_rect.y + 30 + i * 20))

    def draw_input_bar(self):
        box_color = PANEL
        border_col = ACCENT if self.input_active else BORDER
        
        draw_shadow(self.screen, self.input_box, radius=25, alpha=15, offset=(0,4))
        
        rounded_rect(self.screen, self.input_box, box_color, radius=25)
        rounded_rect(self.screen, self.input_box, border_col, radius=25, width=2)

        txt_rect = pygame.Rect(self.input_box.x + 20, self.input_box.y, self.input_box.width - 70, self.input_box.height)
        if self.input_text:
            txt = self.input_text
            surf = self.font_body.render(txt, True, TEXT_MAIN)
            while surf.get_width() > txt_rect.width and len(txt) > 1:
                txt = txt[1:]
                surf = self.font_body.render(txt, True, TEXT_MAIN)
            self.screen.blit(surf, (txt_rect.x, txt_rect.y + (txt_rect.height - surf.get_height()) // 2))
        else:
            surf = self.font_body.render(self.placeholder, True, TEXT_MUTED)
            self.screen.blit(surf, (txt_rect.x, txt_rect.y + (txt_rect.height - surf.get_height()) // 2))

        # cursor
        if self.input_active and self.cursor_visible:
            txt_w = self.font_body.size(self.input_text)[0] if self.input_text else 0
            cx = txt_rect.x + min(txt_w, txt_rect.width) + 2
            pygame.draw.line(self.screen, ACCENT, (cx, txt_rect.y + 12), (cx, txt_rect.bottom - 12), 2)

        # send button
        can_send = bool(self.input_text.strip()) and not self.loading
        hovering_send = self.send_btn.collidepoint(self.mouse_pos)
        send_color = ACCENT_HOVER if (can_send and hovering_send) else (ACCENT if can_send else BORDER)
        
        rounded_rect(self.screen, self.send_btn, send_color, radius=20)
        cx, cy = self.send_btn.center
        if self.loading:
            angle = (time.time() * 6) % (2 * math.pi)
            for i in range(8):
                a = angle + i * (math.pi / 4)
                alpha = int(255 * (i + 1) / 8)
                ex_ = cx + math.cos(a) * 6
                ey_ = cy + math.sin(a) * 6
                pygame.draw.circle(self.screen, with_alpha(WHITE, alpha)[:3], (int(ex_), int(ey_)), 1.5)
        else:
            icon_col = WHITE if can_send else TEXT_MUTED
            pygame.draw.polygon(self.screen, icon_col, [(cx - 3, cy - 5), (cx - 3, cy + 5), (cx + 5, cy)])

    # ── event handling ────────────────────────────────────────────────────
    def handle_event(self, event):
        if event.type == pygame.QUIT:
            return False

        elif event.type == pygame.KEYDOWN:
            if self.input_active:
                if event.key == pygame.K_RETURN:
                    self.do_generate()
                elif event.key == pygame.K_BACKSPACE:
                    if pygame.key.get_mods() & (pygame.KMOD_CTRL | pygame.KMOD_ALT):
                        self.input_text = ""
                    else:
                        self.input_text = self.input_text[:-1]
                elif event.key == pygame.K_ESCAPE:
                    self.input_active = False
                elif event.key == pygame.K_SPACE and not self.input_active:
                    self._toggle_play()
                else:
                    if event.unicode and len(self.input_text) < 200:
                        self.input_text += event.unicode
            else:
                if event.key == pygame.K_SPACE:
                    self._toggle_play()
                elif event.key == pygame.K_LEFT and self.anim_data:
                    self.playing = False
                    self.current_t = max(0, self.current_t - 0.5)
                elif event.key == pygame.K_RIGHT and self.anim_data:
                    self.playing = False
                    self.current_t = min(self.anim_data["duration"], self.current_t + 0.5)

        elif event.type == pygame.MOUSEBUTTONDOWN:
            mx, my = event.pos
            # Allow clicking anywhere near input area to focus
            self.input_active = self.input_box.collidepoint(mx, my)

            if self.send_btn.collidepoint(mx, my):
                self.do_generate()
                self.input_active = True

            if self.summary_toggle_btn.collidepoint(mx, my):
                self.show_summary = not self.show_summary

            if self.anim_data:
                if self.play_btn.collidepoint(mx, my):
                    self._toggle_play()

                expanded = self.scrubber_rect.inflate(0, 20)
                if expanded.collidepoint(mx, my):
                    self.dragging = True
                    self.playing = False
                    self._seek_from_mouse(mx)

        elif event.type == pygame.MOUSEBUTTONUP:
            self.dragging = False

        return True

    def _toggle_play(self):
        if not self.anim_data:
            return
        if self.current_t >= self.anim_data["duration"]:
            self.current_t = 0
        self.playing = not self.playing

    def _seek_from_mouse(self, mx):
        rel = (mx - self.scrubber_rect.x) / self.scrubber_rect.width
        rel = max(0, min(1, rel))
        self.current_t = rel * self.anim_data["duration"]

    # ── main loop ─────────────────────────────────────────────────────────
    def run(self):
        self.dragging = False
        running = True
        while running:
            dt = self.clock.tick(FPS) / 1000.0
            self.mouse_pos = pygame.mouse.get_pos()

            for event in pygame.event.get():
                if event.type == pygame.VIDEORESIZE:
                    self._update_layout(event.w, event.h)
                elif not self.handle_event(event):
                    running = False

            # logic
            if getattr(self, "dragging", False) and self.anim_data:
                self._seek_from_mouse(self.mouse_pos[0])

            self.cursor_timer += dt
            if self.cursor_timer > 0.5:
                self.cursor_timer = 0
                self.cursor_visible = not self.cursor_visible

            if self.loading:
                self.loading_timer += dt
                if self.loading_timer > 0.35:
                    self.loading_timer = 0
                    self.loading_dots += 1

            if self.anim_data and self.playing:
                self.current_t += dt
                if self.current_t >= self.anim_data.get("duration", 1):
                    self.current_t = self.anim_data.get("duration", 1)
                    self.playing = False

            # draw
            self.screen.fill(BG)
            self.draw_canvas()
            self.draw_explanation()
            self.draw_controls()
            self.draw_summary()
            self.draw_input_bar()
            pygame.display.flip()

        pygame.quit()


if __name__ == "__main__":
    server_thread = threading.Thread(target=apis.run_server, daemon=True)
    server_thread.start()
    print("apis running on http://127.0.0.1:8000  (opening Pygame window...)")

    App().run()
    sys.exit(0)
