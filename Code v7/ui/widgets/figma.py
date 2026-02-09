import customtkinter as ctk

# ===== PILL FUNCTION =====
def create_pill_group(parent, x, y, w, h,
                     fill="#EEEEEE", 
                     radius=20):
    
    pill = ctk.CTkFrame(
        parent,
        width=w,
        height=h,
        fg_color=fill,
        corner_radius=radius,
        border_width=0,
        bg_color="#FFFFFF"
    )
    pill.place(x=x, y=y)
    return pill
# ===== PILL =====
def create_pill_group_set(parent, group):
    pills = {}
    for key, x, y, w, h, fill in group:
        pills.setdefault(key, []).append(
            create_pill_group(
                parent,
                x=x,
                y=y,
                w=w,
                h=h,
                fill=fill
            )
        )
    return pills
# ===== BUTTON FUNCTION =====
def figma_button(parent, text, x, y, w, h,
                 command=None,
                 fill="#EEEEEE",
                 hover="#ccd5ae",
                 text_color="#000000",
                 radius=10,
                 font_size=20):

    btn = ctk.CTkButton(
        parent,
        text=text,
        command=command,
        width=w,
        height=h,
        fg_color=fill,
        hover_color=hover,
        text_color=text_color,
        corner_radius=radius,
        font=ctk.CTkFont("Inter", size=font_size, weight="normal"),
        border_width=0,
        bg_color="#FFFFFF"
    )
    btn.place(x=x, y=y)
    return btn
# ===== BUTTONS =====
def create_button_group(parent, group, w, h, y_offset=0):
    buttons = {}
    for text, x, y in group:
        buttons[text] = figma_button(
            parent,
            text=text,
            x=x,
            y=y + y_offset,
            w=w,
            h=h,
        )
    return buttons
# ===== ENTRY FUNCTION =====
def figma_entry(parent, x, y, w, h,
                placeholder="",
                fill="#EEEEEE",
                text_color="#000000",
                radius=10,
                font_size=16):

    entry = ctk.CTkEntry(
        parent,
        width=w,
        height=h,
        placeholder_text=placeholder,
        text_color=text_color,
        fg_color=fill,
        border_width=0,
        corner_radius=radius,
        font=ctk.CTkFont("Inter", size=font_size, weight="normal"),
        bg_color="#FFFFFF"
    )
    entry.place(x=x, y=y)
    return entry
# ===== ENTRY =====
def create_entry_group(parent, group):
    entries = {}
    for key, x, y, w, h, placeholder in group:
        entries[key] = figma_entry(
            parent,
            x=x, y=y, w=w, h=h,
            placeholder=placeholder
        )
    return entries
# ===== COMBOBOX FUNCTION =====
def figma_combobox(parent, x, y, w, h,
                   values,
                   default=None,
                   fill="#EEEEEE",
                   radius=10,
                   font_size=16):

    combo = ctk.CTkComboBox(
        parent,
        values=values,
        width=w,
        height=h,
        fg_color=fill,
        corner_radius=radius,
        font=ctk.CTkFont("Inter", size=font_size),
        dropdown_font=ctk.CTkFont("Inter", size=font_size, weight="normal"),
        border_width=0,
        bg_color="#FFFFFF"
    )

    if default:
        combo.set(default)

    combo.place(x=x, y=y)
    return combo
# =====COMBOBOX =====
def create_combobox_group(parent, group):
    combos = {}
    for key, x, y, w, h, values, default in group:
        combos[key] = figma_combobox(
            parent,
            x=x, y=y, w=w, h=h,
            values=values,
            default=default
        )
    return combos
# ===== SLIDER FUNCTION =====
def figma_vertical_slider(parent, x, y, h,
                          orientation="vertical",
                          min_val=0,
                          max_val=100,
                          value=50,
                          width=40,
                          radius=10,
                          fill="#FFFFFF",
                          progress_color="#34A3AA",
                          command=None):

    slider = ctk.CTkSlider(
        parent,
        from_=min_val,
        to=max_val,
        orientation=orientation,
        height=h,
        width=width,
        corner_radius=radius,
        fg_color=fill,
        progress_color=progress_color,
        button_color=progress_color,
        button_hover_color=progress_color,
        bg_color="#FFFFFF",
        command=command
    )
    slider.place(x=x, y=y)
    slider.set(value)

    return slider
# ===== SLIDER =====
def create_vertical_slider_group(parent, group):
    sliders = {}
    for key, x, y, h, color in group:
        sliders[key] = figma_vertical_slider(
            parent,
            x=x,
            y=y,
            h=h,
            progress_color=color
        )
    return sliders
# ===== LABEL FUNCTION =====
def create_label(parent, x, y, w, h,
                 text="",
                 fill="#FFFFFF",
                 color="#000000",
                 font_size= 20,
                 anchor="w"):

    lbl = ctk.CTkLabel(
        parent,
        text=text,
        width=w,
        height=h,
        font=ctk.CTkFont("Segoe UI", size=font_size, weight="bold"),
        fg_color=fill,
        text_color=color,
        anchor=anchor
    )
    lbl.place(x=x, y=y)
    return lbl
# ===== LABEL =====
def create_label_group(parent, group):
    labels = {}
    for key, x, y, w, h, font_size, text in group:
        labels[key] = create_label(
            parent,
            x=x,
            y=y,
            w=w,
            h=h,
            font_size=font_size,
            text=text
        )
    return labels