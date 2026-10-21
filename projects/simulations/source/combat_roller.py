"""Combat Lab: a standard-library Python desktop dice workbench."""
import random
import tkinter as tk
from tkinter import ttk, messagebox


def hits(attack_die, defence_die, skill, defence, attacker_ties=True):
    margin = attack_die + skill - defence_die - defence
    return margin >= 0 if attacker_ties else margin > 0


def wound_needed(strength, toughness):
    gap = strength - toughness
    return 2 if gap >= 3 else 3 if gap >= 1 else 4 if gap == 0 else 5 if gap >= -2 else 6


def hit_chance(skill, defence, attacker_ties=True):
    return sum(hits(a, d, skill, defence, attacker_ties)
               for a in range(1, 21) for d in range(1, 21)) / 400


class CombatLab(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('Combat Lab • d20 workbench')
        self.geometry('1180x850')
        self.minsize(1040, 780)
        self.configure(bg='#101827')
        style = ttk.Style(self)
        style.theme_use('clam')
        style.configure('.', background='#101827', foreground='#e5edf7', font=('Helvetica', 12))
        style.configure('TFrame', background='#101827')
        style.configure('TLabelframe', background='#101827', bordercolor='#344258')
        style.configure('TLabelframe.Label', foreground='#72daca', font=('Helvetica', 12, 'bold'))
        style.configure('TButton', background='#263950', padding=8)
        style.map('TButton', background=[('active', '#38536f')])
        style.configure('TEntry', fieldbackground='#edf2f8', foreground='#142033')
        style.configure('TCombobox', fieldbackground='#edf2f8', foreground='#142033')
        style.configure('TCheckbutton', background='#101827')
        self.option_add('*TCombobox*Listbox.foreground', '#142033')
        self.option_add('*TCombobox*Listbox.background', '#edf2f8')
        self.skill = tk.StringVar(value='WS')
        self.ties = tk.BooleanVar(value=True)
        self.wounds = tk.BooleanVar(value=False)
        self.armour = tk.BooleanVar(value=False)
        self.damage = tk.StringVar(value='D3 (1–3)')
        self.manual_a = tk.StringVar()
        self.manual_d = tk.StringVar()
        self.last_roll = None
        self.undo_stack = []
        self.people = []
        outer = ttk.Frame(self, padding=20)
        outer.pack(fill='both', expand=True)
        ttk.Label(outer, text='COMBAT LAB', font=('Helvetica', 25, 'bold')).pack(anchor='w')
        ttk.Label(outer, text='Edit your fighters. Compare the odds. Roll the encounter.', foreground='#a9bbd0').pack(anchor='w', pady=(3, 16))
        body = ttk.Frame(outer)
        body.pack(fill='both', expand=True)
        left = ttk.Frame(body, width=350)
        left.pack(side='left', fill='y', padx=(0, 20))
        right = ttk.Frame(body)
        right.pack(side='left', fill='both', expand=True)
        for i, title in enumerate(('ATTACKER', 'DEFENDER')):
            box = ttk.LabelFrame(left, text=title, padding=10)
            box.pack(fill='x', pady=(0, 10))
            values = {'Name': 'Hero' if i == 0 else 'Opponent', 'WS': 4, 'RS': 2,
                      'MS': 3, 'DEF': 0, 'SPD': 3, 'HP': 8, 'Max HP': 8}
            fields = {key: tk.StringVar(value=str(value)) for key, value in values.items()}
            self.people.append(fields)
            ttk.Entry(box, textvariable=fields['Name'], width=30).grid(row=0, column=0, columnspan=5, sticky='ew', pady=(0, 8))
            for col, key in enumerate(('WS', 'RS', 'MS', 'DEF', 'SPD')):
                ttk.Label(box, text=key).grid(row=1, column=col)
                ttk.Entry(box, textvariable=fields[key], width=5).grid(row=2, column=col, padx=3)
            ttk.Label(box, text='HP / max').grid(row=3, column=0, columnspan=2, pady=9)
            ttk.Entry(box, textvariable=fields['HP'], width=5).grid(row=3, column=2)
            ttk.Entry(box, textvariable=fields['Max HP'], width=5).grid(row=3, column=3)
            ttk.Button(box, text='Roll core · 5d6', command=lambda n=i: self.roll_core(n)).grid(row=4, column=0, columnspan=3, sticky='ew')
            ttk.Button(box, text='Heal', command=lambda n=i: self.heal(n)).grid(row=4, column=3, columnspan=2, sticky='ew')
        options = ttk.LabelFrame(left, text='RULES TO EXPERIMENT WITH', padding=10)
        options.pack(fill='x')
        self.combo(options, 'Attack skill', self.skill, ('WS', 'RS', 'MS'), 0)
        self.combo(options, 'Damage die', self.damage, ('D3 (1–3)', 'D6 (1–6)', '3d6 (3–18)'), 1)
        ttk.Checkbutton(options, text='Attacker wins ties', variable=self.ties).grid(row=2, column=0, columnspan=2, sticky='w', pady=4)
        ttk.Checkbutton(options, text='Subtract DEF from damage too', variable=self.armour).grid(row=3, column=0, columnspan=2, sticky='w')
        ttk.Checkbutton(options, text='Use optional wound check', variable=self.wounds).grid(row=4, column=0, columnspan=2, sticky='w', pady=4)
        self.toughness = tk.StringVar(value='4')
        ttk.Label(options, text='Toughness').grid(row=5, column=0, sticky='w')
        ttk.Entry(options, textvariable=self.toughness, width=8).grid(row=5, column=1, sticky='w')
        ttk.Label(options, text='Wound mode: damage roll acts as Strength.\nSPD is kept for movement and turn order.\nNo automatic natural 1 / 20 rule.', foreground='#a9bbd0', font=('Helvetica', 10)).grid(row=6, column=0, columnspan=2, sticky='w', pady=(8, 0))
        ttk.Button(left, text='Swap attacker ↔ defender', command=self.swap).pack(fill='x', pady=10)
        self.odds = ttk.Label(right, font=('Helvetica', 18, 'bold'), foreground='#72daca')
        self.odds.pack(anchor='w')
        ttk.Label(right, text='20 × 20 outcomes · columns = attack d20 · rows = defence d20', foreground='#a9bbd0').pack(anchor='w', pady=(5, 0))
        self.canvas = tk.Canvas(right, background='#101827', highlightthickness=0, height=400)
        self.canvas.pack(fill='both', expand=True, pady=6)
        self.canvas.bind('<Configure>', lambda _: self.refresh())
        self.canvas.bind('<Button-1>', self.pick_cell)
        ttk.Label(right, text='Green = hit   •   Slate = miss   •   Click a cell to choose dice', foreground='#a9bbd0').pack(anchor='w')
        rolls = ttk.Frame(right)
        rolls.pack(fill='x', pady=10)
        for label, var in (('Attack d20', self.manual_a), ('Defence d20', self.manual_d)):
            ttk.Label(rolls, text=label).pack(side='left', padx=(0, 6))
            ttk.Entry(rolls, textvariable=var, width=5).pack(side='left', padx=(0, 14))
        ttk.Label(rolls, text='Blank = random', foreground='#a9bbd0').pack(side='left')
        buttons = ttk.Frame(right)
        buttons.pack(fill='x')
        ttk.Button(buttons, text='ROLL ATTACK', command=self.attack).pack(side='left', fill='x', expand=True)
        ttk.Button(buttons, text='Clear dice', command=self.clear_dice).pack(side='left', padx=6)
        ttk.Button(buttons, text='Undo HP', command=self.undo).pack(side='left')
        self.result = ttk.Label(right, text='Ready to roll.', font=('Helvetica', 13, 'bold'), wraplength=650)
        self.result.pack(anchor='w', pady=10)
        self.history = tk.Text(right, height=7, background='#172337', foreground='#e5edf7', relief='flat', font=('Menlo', 11), wrap='word', state='disabled')
        self.history.pack(fill='x')
        for fields in self.people:
            for key in ('WS', 'RS', 'MS', 'DEF'):
                fields[key].trace_add('write', lambda *_: self.refresh())
        for var in (self.skill, self.ties):
            var.trace_add('write', lambda *_: self.refresh())
        self.refresh()

    def combo(self, parent, label, var, values, row):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky='w', pady=4)
        ttk.Combobox(parent, textvariable=var, values=values, state='readonly', width=15).grid(row=row, column=1, sticky='w')

    @staticmethod
    def number(var, label, low=0, high=999):
        try:
            value = int(var.get())
        except ValueError:
            raise ValueError(f'{label}: enter a whole number.') from None
        if not low <= value <= high:
            raise ValueError(f'{label}: use {low}–{high}.')
        return value

    def stats(self):
        return (self.number(self.people[0][self.skill.get()], self.skill.get()),
                self.number(self.people[1]['DEF'], 'Defence'))

    def refresh(self):
        self.canvas.delete('all')
        try:
            skill, defence = self.stats()
        except ValueError:
            self.odds.configure(text='Enter valid stats to see the grid')
            return
        self.odds.configure(text=f'{hit_chance(skill, defence, self.ties.get()):.2%} to hit  ·  {self.skill.get()} {skill} vs DEF {defence}')
        size = max(1, min((self.canvas.winfo_width() - 35) / 20, (self.canvas.winfo_height() - 28) / 20))
        self.cell_size = size
        for n in range(1, 21):
            self.canvas.create_text(30 + (n - .5) * size, 12, text=str(n), fill='#a9bbd0', font=('Helvetica', 9))
            self.canvas.create_text(13, 25 + (n - .5) * size, text=str(n), fill='#a9bbd0', font=('Helvetica', 9))
        for a in range(1, 21):
            for d in range(1, 21):
                x, y = 30 + (a - 1) * size, 25 + (d - 1) * size
                selected = self.last_roll == (a, d)
                self.canvas.create_rectangle(x + 1, y + 1, x + size - 1, y + size - 1,
                    fill='#218a79' if hits(a, d, skill, defence, self.ties.get()) else '#29374b',
                    outline='#ffffff' if selected else '', width=2)

    def pick_cell(self, event):
        if not hasattr(self, 'cell_size'):
            return
        a, d = int((event.x - 30) // self.cell_size) + 1, int((event.y - 25) // self.cell_size) + 1
        if 1 <= a <= 20 and 1 <= d <= 20:
            self.manual_a.set(str(a))
            self.manual_d.set(str(d))
            self.last_roll = (a, d)
            self.refresh()

    def log(self, text):
        self.history.configure(state='normal')
        self.history.insert('end', text + '\n\n')
        self.history.see('end')
        self.history.configure(state='disabled')

    def attack(self):
        try:
            skill, defence = self.stats()
            hp_values = []
            for person in self.people:
                maximum = self.number(person['Max HP'], 'Max HP', 1)
                hp_values.append(self.number(person['HP'], 'HP', 0, maximum))
            if 0 in hp_values:
                raise ValueError('A fighter is Down (0 HP). Heal them before another attack.')
            toughness = self.number(self.toughness, 'Toughness', 0) if self.wounds.get() else 0
            a = self.number(self.manual_a, 'Attack die', 1, 20) if self.manual_a.get().strip() else random.randint(1, 20)
            d = self.number(self.manual_d, 'Defence die', 1, 20) if self.manual_d.get().strip() else random.randint(1, 20)
        except ValueError as error:
            messagebox.showerror('Check your values', str(error))
            return
        self.last_roll = (a, d)
        hit = hits(a, d, skill, defence, self.ties.get())
        text = f'{self.people[0]["Name"].get()}: {a} + {skill} = {a + skill} vs {self.people[1]["Name"].get()}: {d} + {defence} = {d + defence} → {"HIT" if hit else "MISS"}'
        if hit:
            mode = self.damage.get()
            dice = [random.randint(1, 6) for _ in range(3)] if mode.startswith('3d6') else [random.randint(1, 3 if mode.startswith('D3') else 6)]
            raw = sum(dice)
            dealt = max(0, raw - (defence if self.armour.get() else 0))
            text += f'\n{mode}: {" + ".join(map(str, dice))} = {raw}.'
            if self.wounds.get():
                needed = wound_needed(raw, toughness)
                wound_die = random.randint(1, 6)
                if wound_die < needed:
                    dealt = 0
                text += f' Wound needs {needed}+; rolled {wound_die}: {"wound" if wound_die >= needed else "no wound"}.'
            if self.armour.get():
                text += f' DEF reduction: {defence}.'
            self.undo_stack.append((self.people[1], hp_values[1]))
            remaining = max(0, hp_values[1] - dealt)
            self.people[1]['HP'].set(str(remaining))
            text += f' Damage {dealt}; HP {hp_values[1]} → {remaining}{" · DOWN" if remaining == 0 else ""}.'
        self.result.configure(text=text)
        self.log(text)
        self.refresh()

    def roll_core(self, index):
        for key in ('WS', 'RS', 'MS', 'DEF', 'SPD'):
            self.people[index][key].set(str(random.randint(1, 6)))
        self.log(f'{self.people[index]["Name"].get()} rolled 5d6: ' + ', '.join(f'{key} {self.people[index][key].get()}' for key in ('WS', 'RS', 'MS', 'DEF', 'SPD')))

    def heal(self, index):
        try:
            maximum = self.number(self.people[index]['Max HP'], 'Max HP', 1)
        except ValueError as error:
            messagebox.showerror('Check your values', str(error))
            return
        self.people[index]['HP'].set(str(maximum))
        self.undo_stack.clear()
        self.log(f'{self.people[index]["Name"].get()} healed to {maximum} HP.')

    def swap(self):
        snapshots = [{key: var.get() for key, var in fields.items()} for fields in self.people]
        for i, fields in enumerate(self.people):
            for key, var in fields.items():
                var.set(snapshots[1 - i][key])
        self.undo_stack.clear()
        self.clear_dice()
        self.result.configure(text='Sides swapped. Ready to roll.')

    def clear_dice(self):
        self.manual_a.set('')
        self.manual_d.set('')
        self.last_roll = None
        self.refresh()

    def undo(self):
        if self.undo_stack:
            person, hp = self.undo_stack.pop()
            person['HP'].set(str(hp))
            self.result.configure(text=f'HP restored to {hp}.')
            self.log(f'Undo: {person["Name"].get()} HP restored to {hp}.')


if __name__ == '__main__':
    CombatLab().mainloop()
