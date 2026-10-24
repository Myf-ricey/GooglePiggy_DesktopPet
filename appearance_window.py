"""A modeless native settings window; only queues messages to the pet UI thread."""
from appearance import Appearance, RANGES, COLORS


class AppearanceWindow:
    def __init__(self, values, events):
        self.events = events
        self.alive = True
        self.pumping = False
        self.run(dict(values))

    def show(self):
        self.root.deiconify()
        self.root.lift()

    def close(self):
        if self.alive:
            self.alive = False
            self.events.put(('closed', None))
            self.root.destroy()

    def update(self):
        # Tk objects are created, pumped and destroyed on the Win32 UI thread.
        # A worker-owned interpreter can crash during Python's later GC.
        if self.alive and not self.pumping:
            self.pumping = True
            try:
                self.root.update()
            finally:
                self.pumping = False

    def run(self, values):
        import tkinter as tk
        from tkinter import ttk, colorchooser
        root = tk.Tk()
        self.root = root
        root.title('猪猪桌宠 · 外观')
        root.resizable(False, False)
        root.attributes('-topmost', True)
        frame = ttk.Frame(root, padding=18)
        frame.grid(sticky='nsew')
        ttk.Label(frame, text='调整外观', font=('Microsoft YaHei UI', 16, 'bold')).grid(row=0, column=0, columnspan=3, sticky='w', pady=(0, 8))
        labels = ['猪猪大小', '对话框大小', '任务栏大小', '对话框背景不透明度', '按钮底色不透明度', '任务栏背景不透明度', '对话框上下距离', '任务栏与猪猪距离']
        variables, displays = {}, {}
        updating = False

        def changed(key, value):
            if updating:
                return
            value = round(float(value), 2)
            values[key] = value
            displays[key].set(f'{value:.0f}' if key.endswith('Gap') else f'{value:.0%}')
            self.events.put(('values', {key: value}))

        for row, (key, label) in enumerate(zip(RANGES, labels), 1):
            low, high, _ = RANGES[key]
            ttk.Label(frame, text=label).grid(row=row, column=0, sticky='w', pady=5)
            variable = tk.DoubleVar(value=values[key])
            variables[key] = variable
            display = tk.StringVar(value=f'{values[key]:.0f}' if key.endswith('Gap') else f'{values[key]:.0%}')
            displays[key] = display
            ttk.Scale(frame, from_=low, to=high, variable=variable, length=230,
                      command=lambda v, k=key: changed(k, v)).grid(row=row, column=1, padx=12)
            ttk.Label(frame, textvariable=display, width=6).grid(row=row, column=2)

        color_buttons = {}
        def choose(key):
            color = colorchooser.askcolor(color=values[key] or '#fdf9f6', parent=root, title='选择颜色')[1]
            if color:
                values[key] = color
                color_buttons[key].configure(text=color)
                self.events.put(('values', {key: color}))

        for row, (key, label) in enumerate(zip(COLORS, ['对话框背景颜色', '任务栏背景颜色', '对话框文字颜色', '按钮文字颜色', '任务栏文字颜色']), 9):
            ttk.Label(frame, text=label).grid(row=row, column=0, sticky='w', pady=5)
            button = ttk.Button(frame, text=values[key] or '默认', command=lambda k=key: choose(k))
            button.grid(row=row, column=1, sticky='ew', padx=12)
            color_buttons[key] = button

        previews = {}
        preview_row = 9 + len(COLORS)
        for row, key, label in [(preview_row, 'dialog', '在猪猪旁预览对话框'), (preview_row+1, 'task', '在猪猪旁预览任务栏')]:
            variable = tk.BooleanVar(value=False)
            previews[key] = variable
            ttk.Checkbutton(frame, text=label, variable=variable,
                command=lambda k=key, v=variable: self.events.put(('preview', (k, v.get())))).grid(row=row, column=0, columnspan=3, sticky='w', pady=5)

        def reset():
            nonlocal updating
            updating = True
            values.update(Appearance().values)
            for key, var in variables.items():
                var.set(values[key])
                displays[key].set(f'{values[key]:.0f}' if key.endswith('Gap') else f'{values[key]:.0%}')
            for key, button in color_buttons.items():
                button.configure(text='默认')
            updating = False
            self.events.put(('values', dict(values)))

        ttk.Label(frame, text='即时保存 · 预览不会创建任务或发送权限决定', foreground='#70666b').grid(row=preview_row+2, column=0, columnspan=3, pady=(10, 5))
        ttk.Button(frame, text='恢复默认外观', command=reset).grid(row=preview_row+3, column=0, columnspan=3, sticky='ew', pady=6)

        root.protocol('WM_DELETE_WINDOW', self.close)
        root.update_idletasks()
