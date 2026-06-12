import re

def replace_in_file(filepath, replacements):
    with open(filepath, 'r') as f:
        content = f.read()
    
    for old, new in replacements:
        # Use regex to only replace whole words
        content = re.sub(r'\b' + re.escape(old) + r'\b', new, content)
        
    with open(filepath, 'w') as f:
        f.write(content)

replacements = [
    ("draw_object", "paint_object_on_screen"),
    ("draw_vectors", "paint_physics_arrows"),
    ("rounded_rect", "draw_rectangle_with_soft_corners"),
    ("draw_shadow", "paint_drop_shadow"),
    ("wrap_text", "split_text_into_readable_lines"),
    ("get_current_narration", "find_what_to_say_right_now"),
    ("fetch_animation", "ask_backend_for_animation"),
    ("do_generate", "start_asking_ai_for_scene"),
    ("draw_canvas", "paint_the_whiteboard_and_scene"),
    ("draw_explanation", "show_the_teacher_explanation"),
    ("draw_controls", "paint_play_bar_and_buttons"),
    ("draw_summary", "show_key_concepts_card"),
    ("draw_input_bar", "paint_the_chat_box"),
    ("_toggle_play", "play_or_pause_animation"),
    ("_seek_from_mouse", "jump_to_time_from_click"),
    ("get_prop_smooth", "interpolate_with_smooth_fades"),
    ("get_prop", "figure_out_exact_value"),
    ("compute_velocity", "calculate_current_speed"),
    ("compute_rolling_rotation", "figure_out_how_much_it_rolled"),
    ("hex_to_rgb", "convert_hex_color_to_rgb"),
    ("with_alpha", "add_transparency_to_color"),
]

replace_in_file("gui.py", replacements)
print("Replaced in gui.py!")
