from __future__ import annotations

import json
import os
import sys
import struct
from dataclasses import asdict
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext, simpledialog, colorchooser

from .core import (
    BinarySource, ChangeSet, Change, ProjectState, MappedRecord,
    parse_int, decode_scalar, encode_scalar, human_size,
)
from .tim import scan_tims, decode_tim

try:
    from PIL import Image, ImageTk, ImageDraw
except Exception:
    Image = ImageTk = ImageDraw = None


def resource_path(rel: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    return base / rel


class VH2StudioApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("PS1 Archaeology Studio — Vandal Hearts II Profile")
        self.root.geometry("1380x880")
        self.root.minsize(1100, 720)

        self.source: BinarySource | None = None
        self.changeset: ChangeSet | None = None
        self.project = ProjectState()
        self.project_path: Path | None = None
        self.current_scan_results: list[int] = []
        self.current_hex_offset = 0
        self.tim_results = []
        self.current_tim_image = None
        self.current_tim_photo = None
        self.current_asset_image = None
        self.current_asset_path: str | None = None
        self.appearance_frames: list[Image.Image] = [] if Image else []
        self.appearance_frame_names: list[str] = []
        self.appearance_play_job = None
        self.appearance_play_index = 0
        self.direction_order = ["N", "E", "S", "W"]
        self.current_direction_index = 0
        self.dialogue_results: list[dict] = []
        self.portrait_image = None
        self.portrait_photo = None
        self.scene_tool = "terrain"
        self.scene_terrain = "grass"
        self.scene_selected_unit = None
        self.scene_tile_size = 42

        self.profile = self._load_profile()
        self._build_style()
        self._build_ui()
        self._bind_shortcuts()
        self.log("Aplicativo iniciado em modo seguro. O arquivo original nunca é alterado diretamente.")
        self._refresh_all()

    def _load_profile(self):
        p = resource_path("profiles/vh2.json")
        if not p.exists():
            # when running as package from source
            p = Path(__file__).resolve().parents[1] / "profiles" / "vh2.json"
        return json.loads(p.read_text(encoding="utf-8"))

    def _build_style(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure("TButton", padding=(8, 5), font=("Segoe UI", 9))
        style.configure("Primary.TButton", font=("Segoe UI", 9, "bold"))
        style.configure("Danger.TButton", font=("Segoe UI", 9, "bold"))
        style.configure("Status.TLabel", font=("Segoe UI", 9, "bold"))
        style.configure("Title.TLabel", font=("Segoe UI", 16, "bold"))
        style.configure("SubTitle.TLabel", font=("Segoe UI", 11, "bold"))

    def _build_ui(self):
        self._build_toolbar()
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=8, pady=(2, 4))

        self.tab_dash = ttk.Frame(self.notebook, padding=10)
        self.tab_hex = ttk.Frame(self.notebook, padding=8)
        self.tab_records = ttk.Frame(self.notebook, padding=8)
        self.tab_graphics = ttk.Frame(self.notebook, padding=8)
        self.tab_dialogue = ttk.Frame(self.notebook, padding=8)
        self.tab_scene = ttk.Frame(self.notebook, padding=8)
        self.tab_changes = ttk.Frame(self.notebook, padding=8)

        self.notebook.add(self.tab_dash, text="🏠 Dashboard")
        self.notebook.add(self.tab_hex, text="🔎 Hex & Scan")
        self.notebook.add(self.tab_records, text="🧬 Structs / Itens / Magias")
        self.notebook.add(self.tab_graphics, text="🎨 TIM & Aparência")
        self.notebook.add(self.tab_dialogue, text="💬 Falas & Faces")
        self.notebook.add(self.tab_scene, text="🗺 Scene Preview")
        self.notebook.add(self.tab_changes, text="🧩 ChangeSet & Build")

        self._build_dashboard()
        self._build_hex_scan()
        self._build_records()
        self._build_graphics()
        self._build_dialogue()
        self._build_scene()
        self._build_changes()

        log_frame = ttk.LabelFrame(self.root, text="Console", padding=5)
        log_frame.pack(fill=tk.X, padx=8, pady=(0, 8))
        self.txt_log = scrolledtext.ScrolledText(log_frame, height=5, state="disabled", font=("Consolas", 9))
        self.txt_log.pack(fill=tk.BOTH, expand=True)

    def _build_toolbar(self):
        bar = ttk.Frame(self.root, padding=(8, 6))
        bar.pack(fill=tk.X)
        ttk.Button(bar, text="＋ Novo Projeto", style="Primary.TButton", command=self.new_project).pack(side=tk.LEFT, padx=2)
        ttk.Button(bar, text="📂 Abrir Projeto", command=self.open_project).pack(side=tk.LEFT, padx=2)
        ttk.Button(bar, text="💾 Salvar Projeto", command=self.save_project).pack(side=tk.LEFT, padx=2)
        ttk.Separator(bar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=6)
        ttk.Button(bar, text="📀 Abrir BIN/EXE", style="Primary.TButton", command=self.open_source).pack(side=tk.LEFT, padx=2)
        ttk.Button(bar, text="✓ Verificar Hash", command=self.verify_source_hash).pack(side=tk.LEFT, padx=2)
        ttk.Separator(bar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=6)
        ttk.Button(bar, text="↶ Undo", command=self.undo).pack(side=tk.LEFT, padx=2)
        ttk.Button(bar, text="↷ Redo", command=self.redo).pack(side=tk.LEFT, padx=2)
        self.lbl_top_status = ttk.Label(bar, text="● SEM FONTE", style="Status.TLabel")
        self.lbl_top_status.pack(side=tk.RIGHT, padx=8)

    def _build_dashboard(self):
        ttk.Label(self.tab_dash, text="PS1 Archaeology Studio", style="Title.TLabel").pack(anchor=tk.W)
        ttk.Label(self.tab_dash, text="Perfil especializado: Vandal Hearts II — edição segura por evidências e ChangeSets").pack(anchor=tk.W, pady=(0, 12))

        cards = ttk.Frame(self.tab_dash)
        cards.pack(fill=tk.X)
        self.lbl_card_source = self._status_card(cards, "FONTE", "Nenhuma")
        self.lbl_card_hash = self._status_card(cards, "SHA-256", "—")
        self.lbl_card_changes = self._status_card(cards, "ALTERAÇÕES", "0")
        self.lbl_card_records = self._status_card(cards, "MAPEAMENTOS", "0")

        info = ttk.LabelFrame(self.tab_dash, text="Estado do projeto", padding=10)
        info.pack(fill=tk.BOTH, expand=True, pady=12)
        self.txt_dashboard = scrolledtext.ScrolledText(info, state="disabled", font=("Consolas", 10))
        self.txt_dashboard.pack(fill=tk.BOTH, expand=True)

        actions = ttk.Frame(self.tab_dash)
        actions.pack(fill=tk.X)
        ttk.Button(actions, text="Abrir fonte", command=self.open_source).pack(side=tk.LEFT, padx=3)
        ttk.Button(actions, text="Ir para Hex/Scan", command=lambda: self.notebook.select(self.tab_hex)).pack(side=tk.LEFT, padx=3)
        ttk.Button(actions, text="Validar ChangeSet", command=self.validate_changes).pack(side=tk.LEFT, padx=3)
        ttk.Button(actions, text="Construir cópia de teste", command=self.build_test_copy).pack(side=tk.RIGHT, padx=3)

    def _status_card(self, parent, title, value):
        f = ttk.LabelFrame(parent, text=title, padding=10)
        f.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)
        lbl = ttk.Label(f, text=value, style="SubTitle.TLabel")
        lbl.pack(anchor=tk.W)
        return lbl

    def _build_hex_scan(self):
        pan = ttk.Panedwindow(self.tab_hex, orient=tk.HORIZONTAL)
        pan.pack(fill=tk.BOTH, expand=True)
        left = ttk.Frame(pan, padding=4)
        right = ttk.Frame(pan, padding=4)
        pan.add(left, weight=1)
        pan.add(right, weight=2)

        scan_box = ttk.LabelFrame(left, text="Busca", padding=8)
        scan_box.pack(fill=tk.X)
        ttk.Label(scan_box, text="Modo:").grid(row=0, column=0, sticky=tk.W)
        self.cmb_scan_mode = ttk.Combobox(scan_box, values=["Valor", "Hex/Wildcard", "Texto"], state="readonly", width=14)
        self.cmb_scan_mode.set("Valor")
        self.cmb_scan_mode.grid(row=0, column=1, sticky=tk.EW, padx=4)
        ttk.Label(scan_box, text="Consulta:").grid(row=1, column=0, sticky=tk.W, pady=4)
        self.ent_scan_query = ttk.Entry(scan_box)
        self.ent_scan_query.grid(row=1, column=1, sticky=tk.EW, padx=4)
        self.ent_scan_query.insert(0, "0xB6")
        ttk.Label(scan_box, text="Tipo/Encoding:").grid(row=2, column=0, sticky=tk.W)
        self.cmb_scan_dtype = ttk.Combobox(scan_box, values=["u8", "u16le", "u32le", "s8", "s16le", "s32le", "shift_jis", "ascii"], state="readonly")
        self.cmb_scan_dtype.set("u16le")
        self.cmb_scan_dtype.grid(row=2, column=1, sticky=tk.EW, padx=4)
        ttk.Button(scan_box, text="🔎 Buscar", style="Primary.TButton", command=self.run_scan).grid(row=3, column=0, columnspan=2, sticky=tk.EW, pady=(8,0))
        scan_box.columnconfigure(1, weight=1)

        resbox = ttk.LabelFrame(left, text="Resultados", padding=4)
        resbox.pack(fill=tk.BOTH, expand=True, pady=8)
        self.tree_scan = ttk.Treeview(resbox, columns=("off","ram","preview"), show="headings", height=18)
        for c,t,w in [("off","File offset",95),("ram","RAM",105),("preview","Preview",210)]:
            self.tree_scan.heading(c, text=t)
            self.tree_scan.column(c, width=w, anchor=tk.W)
        self.tree_scan.pack(fill=tk.BOTH, expand=True)
        self.tree_scan.bind("<<TreeviewSelect>>", self.on_scan_select)
        ttk.Button(left, text="📌 Usar offset selecionado no Struct Lab", command=self.scan_to_record_lab).pack(fill=tk.X)

        nav = ttk.Frame(right)
        nav.pack(fill=tk.X)
        ttk.Label(nav, text="Offset:").pack(side=tk.LEFT)
        self.ent_hex_offset = ttk.Entry(nav, width=14)
        self.ent_hex_offset.insert(0, "0x0")
        self.ent_hex_offset.pack(side=tk.LEFT, padx=4)
        ttk.Label(nav, text="Bytes:").pack(side=tk.LEFT)
        self.spn_hex_size = ttk.Spinbox(nav, from_=64, to=4096, increment=64, width=8)
        self.spn_hex_size.set("512")
        self.spn_hex_size.pack(side=tk.LEFT, padx=4)
        ttk.Button(nav, text="Ir", command=self.goto_hex).pack(side=tk.LEFT, padx=3)
        ttk.Button(nav, text="◀", command=lambda: self.shift_hex(-1)).pack(side=tk.LEFT)
        ttk.Button(nav, text="▶", command=lambda: self.shift_hex(1)).pack(side=tk.LEFT)

        hexbox = ttk.LabelFrame(right, text="Hex Viewer (somente leitura)", padding=5)
        hexbox.pack(fill=tk.BOTH, expand=True, pady=6)
        self.txt_hex = scrolledtext.ScrolledText(hexbox, font=("Consolas", 10), wrap=tk.NONE, state="disabled")
        self.txt_hex.pack(fill=tk.BOTH, expand=True)

        inspector = ttk.LabelFrame(right, text="Inspector", padding=6)
        inspector.pack(fill=tk.X)
        self.lbl_inspector = ttk.Label(inspector, text="Selecione um offset para interpretar.", font=("Consolas", 9))
        self.lbl_inspector.pack(anchor=tk.W)

    def _build_records(self):
        top = ttk.Frame(self.tab_records)
        top.pack(fill=tk.X)
        ttk.Label(top, text="Base offset:").pack(side=tk.LEFT)
        self.ent_record_base = ttk.Entry(top, width=14)
        self.ent_record_base.pack(side=tk.LEFT, padx=4)
        ttk.Label(top, text="Tipo:").pack(side=tk.LEFT)
        self.cmb_record_type = ttk.Combobox(top, values=["item", "magic"], state="readonly", width=12)
        self.cmb_record_type.set("item")
        self.cmb_record_type.pack(side=tk.LEFT, padx=4)
        ttk.Button(top, text="Mapear registro", style="Primary.TButton", command=self.map_record).pack(side=tk.LEFT, padx=4)
        ttk.Button(top, text="＋ Definir campo", command=self.add_custom_field).pack(side=tk.LEFT, padx=4)
        ttk.Button(top, text="Atualizar leitura", command=self.refresh_record_fields).pack(side=tk.LEFT, padx=4)

        pan = ttk.Panedwindow(self.tab_records, orient=tk.HORIZONTAL)
        pan.pack(fill=tk.BOTH, expand=True, pady=8)
        left = ttk.Frame(pan)
        right = ttk.Frame(pan)
        pan.add(left, weight=1)
        pan.add(right, weight=1)

        recbox = ttk.LabelFrame(left, text="Registros mapeados", padding=5)
        recbox.pack(fill=tk.BOTH, expand=True)
        self.tree_records = ttk.Treeview(recbox, columns=("type","base","label","evidence"), show="headings")
        for c,t,w in [("type","Tipo",80),("base","Base",100),("label","Rótulo",180),("evidence","Evidência",130)]:
            self.tree_records.heading(c, text=t); self.tree_records.column(c,width=w)
        self.tree_records.pack(fill=tk.BOTH, expand=True)
        self.tree_records.bind("<<TreeviewSelect>>", self.on_record_select)

        fldbox = ttk.LabelFrame(right, text="Campos do registro", padding=5)
        fldbox.pack(fill=tk.BOTH, expand=True)
        self.tree_fields = ttk.Treeview(fldbox, columns=("name","rel","dtype","value","evidence"), show="headings")
        for c,t,w in [("name","Campo",150),("rel","+Offset",75),("dtype","Tipo",80),("value","Valor",160),("evidence","Evidência",125)]:
            self.tree_fields.heading(c,text=t); self.tree_fields.column(c,width=w)
        self.tree_fields.pack(fill=tk.BOTH, expand=True)
        self.tree_fields.bind("<Double-1>", lambda e: self.edit_selected_field())
        buttons = ttk.Frame(right)
        buttons.pack(fill=tk.X, pady=5)
        ttk.Button(buttons, text="✏ Editar campo selecionado", command=self.edit_selected_field).pack(side=tk.LEFT, padx=3)
        ttk.Button(buttons, text="🔗 Ir ao Hex", command=self.field_to_hex).pack(side=tk.LEFT, padx=3)
        ttk.Button(buttons, text="Remover mapeamento", command=self.remove_record).pack(side=tk.RIGHT, padx=3)
        ttk.Label(self.tab_records, text="Nota: campos LEGACY-HYPOTHESIS são exploratórios; somente PROVEN/USER-MAPPED devem ser tratados como conhecidos.").pack(anchor=tk.W)

    def _build_graphics(self):
        pan = ttk.Panedwindow(self.tab_graphics, orient=tk.HORIZONTAL)
        pan.pack(fill=tk.BOTH, expand=True)
        left = ttk.Frame(pan, padding=4)
        right = ttk.Frame(pan, padding=4)
        pan.add(left, weight=1)
        pan.add(right, weight=2)

        ttk.Button(left, text="🔎 Scan TIM", style="Primary.TButton", command=self.scan_tim_assets).pack(fill=tk.X, pady=3)
        self.tree_tim = ttk.Treeview(left, columns=("off","bpp","size","clut"), show="headings", height=18)
        for c,t,w in [("off","Offset",95),("bpp","BPP",45),("size","Dimensão",90),("clut","CLUT",55)]:
            self.tree_tim.heading(c,text=t); self.tree_tim.column(c,width=w)
        self.tree_tim.pack(fill=tk.BOTH, expand=True, pady=4)
        self.tree_tim.bind("<<TreeviewSelect>>", self.on_tim_select)
        ttk.Button(left, text="📤 Exportar TIM como PNG", command=self.export_current_tim).pack(fill=tk.X, pady=2)
        ttk.Button(left, text="🖼 Importar PNG para Preview", command=self.import_preview_image).pack(fill=tk.X, pady=2)

        prevbox = ttk.LabelFrame(right, text="Battle Appearance Preview", padding=6)
        prevbox.pack(fill=tk.BOTH, expand=True)
        self.canvas_actor = tk.Canvas(prevbox, bg="#20242b", highlightthickness=0)
        self.canvas_actor.pack(fill=tk.BOTH, expand=True)
        self.canvas_actor.bind("<Configure>", lambda e: self.render_actor_preview())

        controls = ttk.Frame(right)
        controls.pack(fill=tk.X, pady=6)
        ttk.Button(controls, text="← Girar", command=lambda: self.rotate_actor(-1)).pack(side=tk.LEFT, padx=2)
        self.lbl_direction = ttk.Label(controls, text="Direção: N", style="Status.TLabel")
        self.lbl_direction.pack(side=tk.LEFT, padx=8)
        ttk.Button(controls, text="Girar →", command=lambda: self.rotate_actor(1)).pack(side=tk.LEFT, padx=2)
        ttk.Button(controls, text="Usar imagem na direção", command=self.assign_direction_image).pack(side=tk.LEFT, padx=8)
        ttk.Button(controls, text="＋ Frame animação", command=self.add_animation_frame).pack(side=tk.LEFT, padx=2)
        ttk.Button(controls, text="▶ Play", command=self.play_appearance).pack(side=tk.LEFT, padx=2)
        ttk.Button(controls, text="■ Stop", command=self.stop_appearance).pack(side=tk.LEFT, padx=2)
        ttk.Button(controls, text="Exportar GIF", command=self.export_appearance_gif).pack(side=tk.RIGHT, padx=2)

        pal = ttk.Frame(right)
        pal.pack(fill=tk.X)
        ttk.Button(pal, text="🎨 Aplicar tint no preview", command=self.tint_current_asset).pack(side=tk.LEFT, padx=2)
        ttk.Button(pal, text="Limpar animação", command=self.clear_animation).pack(side=tk.LEFT, padx=2)
        self.lbl_graphics_status = ttk.Label(pal, text="Selecione um TIM ou importe PNG.")
        self.lbl_graphics_status.pack(side=tk.LEFT, padx=8)

    def _build_dialogue(self):
        pan = ttk.Panedwindow(self.tab_dialogue, orient=tk.HORIZONTAL)
        pan.pack(fill=tk.BOTH, expand=True)
        left = ttk.Frame(pan, padding=4)
        right = ttk.Frame(pan, padding=4)
        pan.add(left, weight=1)
        pan.add(right, weight=2)

        ctrl = ttk.LabelFrame(left, text="Extrair strings", padding=6)
        ctrl.pack(fill=tk.X)
        ttk.Label(ctrl,text="Encoding:").grid(row=0,column=0,sticky=tk.W)
        self.cmb_text_encoding = ttk.Combobox(ctrl, values=["shift_jis","ascii"], state="readonly", width=12)
        self.cmb_text_encoding.set("shift_jis")
        self.cmb_text_encoding.grid(row=0,column=1,padx=4)
        ttk.Label(ctrl,text="Mín. chars:").grid(row=1,column=0,sticky=tk.W)
        self.spn_text_min = ttk.Spinbox(ctrl, from_=3,to=80,width=8)
        self.spn_text_min.set("5")
        self.spn_text_min.grid(row=1,column=1,padx=4)
        ttk.Button(ctrl,text="🔎 Procurar falas/textos",command=self.scan_strings).grid(row=2,column=0,columnspan=2,sticky=tk.EW,pady=5)

        self.tree_text = ttk.Treeview(left, columns=("off","len","text"), show="headings", height=18)
        for c,t,w in [("off","Offset",90),("len","Bytes",55),("text","Texto",260)]:
            self.tree_text.heading(c,text=t); self.tree_text.column(c,width=w)
        self.tree_text.pack(fill=tk.BOTH, expand=True, pady=5)
        self.tree_text.bind("<<TreeviewSelect>>", self.on_text_select)

        top = ttk.Frame(right)
        top.pack(fill=tk.X)
        ttk.Button(top,text="🙂 Importar retrato",command=self.import_portrait).pack(side=tk.LEFT,padx=2)
        ttk.Label(top,text="Nome:").pack(side=tk.LEFT,padx=(10,2))
        self.ent_speaker = ttk.Entry(top,width=22)
        self.ent_speaker.insert(0,"PERSONAGEM")
        self.ent_speaker.pack(side=tk.LEFT)
        ttk.Button(top,text="Ir ao Hex",command=self.dialogue_to_hex).pack(side=tk.RIGHT,padx=2)

        edit = ttk.LabelFrame(right,text="Texto selecionado / substituição de mesmo tamanho",padding=6)
        edit.pack(fill=tk.X,pady=5)
        self.txt_dialogue_edit = tk.Text(edit,height=5,wrap=tk.WORD)
        self.txt_dialogue_edit.pack(fill=tk.X)
        ttk.Button(edit,text="💾 Encenação segura da substituição",style="Primary.TButton",command=self.stage_dialogue_edit).pack(anchor=tk.E,pady=(5,0))

        preview = ttk.LabelFrame(right,text="Preview de diálogo",padding=6)
        preview.pack(fill=tk.BOTH,expand=True)
        self.canvas_dialogue = tk.Canvas(preview,bg="#171717",highlightthickness=0)
        self.canvas_dialogue.pack(fill=tk.BOTH,expand=True)
        self.canvas_dialogue.bind("<Configure>",lambda e:self.render_dialogue_preview())

    def _build_scene(self):
        top = ttk.Frame(self.tab_scene)
        top.pack(fill=tk.X)
        ttk.Label(top,text="Scene Preview local do projeto — não grava mapa na ROM sem um schema mapeado.",style="Status.TLabel").pack(side=tk.LEFT)
        ttk.Button(top,text="Limpar cena",command=self.clear_scene).pack(side=tk.RIGHT,padx=2)
        ttk.Button(top,text="Salvar no projeto",command=self.save_scene_state).pack(side=tk.RIGHT,padx=2)

        tools = ttk.LabelFrame(self.tab_scene,text="Ferramentas",padding=6)
        tools.pack(fill=tk.X,pady=5)
        ttk.Button(tools,text="Terreno",command=lambda:self.set_scene_tool("terrain")).pack(side=tk.LEFT,padx=2)
        ttk.Button(tools,text="Unidade",command=lambda:self.set_scene_tool("unit")).pack(side=tk.LEFT,padx=2)
        ttk.Button(tools,text="Evento/Fala",command=lambda:self.set_scene_tool("event")).pack(side=tk.LEFT,padx=2)
        ttk.Label(tools,text="Terreno:").pack(side=tk.LEFT,padx=(12,2))
        self.cmb_terrain = ttk.Combobox(tools,values=["grass","stone","water","wall"],state="readonly",width=10)
        self.cmb_terrain.set("grass")
        self.cmb_terrain.pack(side=tk.LEFT)
        ttk.Button(tools,text="▶ Preview da cena",command=self.scene_play_preview).pack(side=tk.RIGHT,padx=2)

        self.canvas_scene = tk.Canvas(self.tab_scene,bg="#111821",highlightthickness=0)
        self.canvas_scene.pack(fill=tk.BOTH,expand=True,pady=4)
        self.canvas_scene.bind("<Button-1>",self.on_scene_click)
        self.canvas_scene.bind("<Configure>",lambda e:self.render_scene())

    def _build_changes(self):
        self.tree_changes = ttk.Treeview(self.tab_changes,columns=("on","off","label","cat","old","new","evidence"),show="headings")
        for c,t,w in [("on","ON",45),("off","Offset",90),("label","Alteração",220),("cat","Categoria",90),("old","Original",140),("new","Novo",140),("evidence","Evidência",120)]:
            self.tree_changes.heading(c,text=t); self.tree_changes.column(c,width=w)
        self.tree_changes.pack(fill=tk.BOTH,expand=True)

        controls = ttk.Frame(self.tab_changes)
        controls.pack(fill=tk.X,pady=6)
        ttk.Button(controls,text="Ativar/Desativar",command=self.toggle_change).pack(side=tk.LEFT,padx=2)
        ttk.Button(controls,text="Remover",command=self.remove_change).pack(side=tk.LEFT,padx=2)
        ttk.Button(controls,text="✓ Validar",command=self.validate_changes).pack(side=tk.LEFT,padx=8)
        ttk.Button(controls,text="📄 Exportar manifesto JSON",command=self.export_manifest).pack(side=tk.LEFT,padx=2)
        ttk.Button(controls,text="🧩 Exportar IPS",command=self.export_ips).pack(side=tk.RIGHT,padx=2)
        ttk.Button(controls,text="🛠 Construir cópia de teste",style="Primary.TButton",command=self.build_test_copy).pack(side=tk.RIGHT,padx=8)

    def _bind_shortcuts(self):
        self.root.bind("<Control-s>", lambda e: self.save_project())
        self.root.bind("<Control-o>", lambda e: self.open_source())
        self.root.bind("<Control-z>", lambda e: self.undo())
        self.root.bind("<Control-y>", lambda e: self.redo())
        self.root.bind("<F5>", lambda e: self._refresh_all())

    # ---------- core project actions ----------
    def new_project(self):
        if self._has_unsaved_changes() and not messagebox.askyesno("Novo projeto", "Há alterações no projeto atual. Continuar e iniciar outro projeto?"):
            return
        name = simpledialog.askstring("Novo projeto", "Nome do projeto:", initialvalue="VH2 Research")
        if not name:
            return
        self.project = ProjectState(name=name)
        self.project_path = None
        self.source = None
        self.changeset = None
        self.current_scan_results = []
        self.log(f"Novo projeto criado: {name}")
        self._refresh_all()
        if messagebox.askyesno("Fonte", "Deseja abrir agora o BIN/ISO/SLUS/PS-X EXE que será usado como fonte?"):
            self.open_source()

    def open_project(self):
        path = filedialog.askopenfilename(filetypes=[("Projeto PS1 Studio","*.ps1studio.json"),("JSON","*.json"),("Todos","*.*")])
        if not path:
            return
        try:
            project = ProjectState.load(path)
            self.project = project
            self.project_path = Path(path)
            self.source = None
            self.changeset = None
            if project.source_path and Path(project.source_path).exists():
                self._load_source_path(project.source_path, restore_changes=True)
            else:
                if project.source_path:
                    messagebox.showwarning("Fonte não encontrada", "O projeto foi aberto, mas o arquivo-fonte original não está no caminho salvo. Use 'Abrir BIN/EXE'.")
            self.log(f"Projeto aberto: {path}")
            self._refresh_all()
        except Exception as e:
            messagebox.showerror("Erro", str(e))

    def save_project(self):
        if self.source:
            self.project.source_path = str(self.source.path)
            self.project.source_sha256 = self.source.sha256
        if self.changeset:
            self.project.changes = [asdict(c) for c in self.changeset.changes]
        if not self.project_path:
            path = filedialog.asksaveasfilename(defaultextension=".ps1studio.json",filetypes=[("Projeto PS1 Studio","*.ps1studio.json")])
            if not path:
                return
            self.project_path = Path(path)
        try:
            self.save_scene_state(silent=True)
            self.project.save(self.project_path)
            self.log(f"Projeto salvo: {self.project_path}")
            messagebox.showinfo("Projeto", "Projeto salvo com sucesso.")
        except Exception as e:
            messagebox.showerror("Erro ao salvar", str(e))

    def open_source(self):
        path = filedialog.askopenfilename(filetypes=[("PS1 / Binários","*.bin *.BIN *.iso *.ISO *.exe *.EXE *.SLUS* *.SLES* *.SCUS* *.SCES*"),("Todos","*.*")])
        if path:
            self._load_source_path(path, restore_changes=False)

    def _load_source_path(self, path, restore_changes=False):
        try:
            src = BinarySource.load(path)
            if self.project.source_sha256 and self.project.source_sha256 != src.sha256:
                if not messagebox.askyesno("Hash diferente", "A fonte selecionada não tem o SHA-256 salvo no projeto. Carregar mesmo assim?\n\nAlterações antigas não serão restauradas automaticamente."):
                    return
                restore_changes = False
            self.source = src
            self.changeset = ChangeSet(src)
            self.project.source_path = str(src.path)
            self.project.source_sha256 = src.sha256
            if restore_changes:
                self.changeset.changes = [Change(**d) for d in self.project.changes]
            self.log(f"Fonte carregada: {src.path.name} ({human_size(src.size)}) SHA256={src.sha256}")
            self._refresh_all()
            self.goto_hex(0)
        except Exception as e:
            messagebox.showerror("Erro ao abrir fonte", str(e))

    def verify_source_hash(self):
        if not self.source:
            messagebox.showwarning("Hash", "Nenhuma fonte carregada.")
            return
        fresh = BinarySource.load(self.source.path)
        ok = fresh.sha256 == self.source.sha256 == self.project.source_sha256
        if ok:
            messagebox.showinfo("Hash", f"PASS\n\nSHA-256:\n{fresh.sha256}")
            self.log("Verificação de integridade da fonte: PASS")
        else:
            messagebox.showerror("Hash", f"FAIL\n\nAtual: {fresh.sha256}\nEsperado: {self.project.source_sha256 or self.source.sha256}")
            self.log("Verificação de integridade da fonte: FAIL")

    def _has_unsaved_changes(self):
        return bool(self.changeset and self.changeset.changes)

    # ---------- scan/hex ----------
    def require_source(self):
        if not self.source:
            messagebox.showwarning("Fonte", "Abra uma fonte primeiro.")
            return False
        return True

    def run_scan(self):
        if not self.require_source(): return
        mode = self.cmb_scan_mode.get()
        q = self.ent_scan_query.get()
        try:
            if mode == "Valor":
                results = self.source.scan_value(parse_int(q), self.cmb_scan_dtype.get())
            elif mode == "Hex/Wildcard":
                results = self.source.scan_hex_pattern(q)
            else:
                enc = self.cmb_scan_dtype.get()
                if enc not in ("shift_jis","ascii"):
                    enc = "shift_jis"
                results = self.source.scan_text(q, enc)
            self.current_scan_results = results
            self.tree_scan.delete(*self.tree_scan.get_children())
            for off in results[:5000]:
                ram = self.source.file_to_ram(off) if self.source.is_psx_exe else None
                prev = self.source.data[off:off+16].hex(" ").upper()
                self.tree_scan.insert("",tk.END,values=(f"0x{off:X}", f"0x{ram:08X}" if ram is not None else "—", prev))
            self.log(f"Scan '{mode}' encontrou {len(results)} ocorrência(s); exibindo {min(len(results),5000)}.")
        except Exception as e:
            messagebox.showerror("Erro no scan", str(e))

    def on_scan_select(self, event=None):
        sel = self.tree_scan.selection()
        if not sel: return
        off = parse_int(self.tree_scan.item(sel[0],"values")[0])
        self.goto_hex(off)

    def scan_to_record_lab(self):
        sel = self.tree_scan.selection()
        if not sel:
            messagebox.showwarning("Offset", "Selecione um resultado.")
            return
        off = self.tree_scan.item(sel[0],"values")[0]
        self.ent_record_base.delete(0,tk.END); self.ent_record_base.insert(0,off)
        self.notebook.select(self.tab_records)

    def goto_hex(self, offset=None):
        if not self.require_source(): return
        try:
            off = parse_int(self.ent_hex_offset.get()) if offset is None else int(offset)
            size = parse_int(self.spn_hex_size.get(), 512)
            off = max(0, min(off, max(0,self.source.size-1)))
            size = max(16, min(size, 8192))
            self.current_hex_offset = off
            self.ent_hex_offset.delete(0,tk.END); self.ent_hex_offset.insert(0,f"0x{off:X}")
            data = self.source.data[off:min(self.source.size,off+size)]
            lines=[]
            for i in range(0,len(data),16):
                chunk=data[i:i+16]
                hx=" ".join(f"{b:02X}" for b in chunk)
                asc="".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
                lines.append(f"{off+i:08X}  {hx:<47}  |{asc}|")
            self.txt_hex.config(state="normal"); self.txt_hex.delete("1.0",tk.END); self.txt_hex.insert("1.0","\n".join(lines)); self.txt_hex.config(state="disabled")
            self.update_inspector(off)
        except Exception as e:
            messagebox.showerror("Hex", str(e))

    def shift_hex(self, direction):
        size=parse_int(self.spn_hex_size.get(),512)
        self.goto_hex(self.current_hex_offset + direction*size)

    def update_inspector(self, off):
        if not self.source: return
        b=self.source.data[off:off+8]
        vals=[f"FILE 0x{off:X}"]
        if self.source.is_psx_exe: vals.append(f"RAM 0x{self.source.file_to_ram(off):08X}")
        if len(b)>=1: vals.append(f"u8={b[0]}  s8={struct.unpack('<b',b[:1])[0]}")
        if len(b)>=2: vals.append(f"u16={struct.unpack('<H',b[:2])[0]}  s16={struct.unpack('<h',b[:2])[0]}")
        if len(b)>=4: vals.append(f"u32=0x{struct.unpack('<I',b[:4])[0]:08X}")
        vals.append("HEX="+b.hex(" ").upper())
        self.lbl_inspector.config(text="   |   ".join(vals))

    # ---------- record lab ----------
    def map_record(self):
        if not self.require_source(): return
        try:
            base=parse_int(self.ent_record_base.get())
            if base is None or not 0 <= base < self.source.size: raise ValueError("Base inválida.")
            typ=self.cmb_record_type.get()
            label=simpledialog.askstring("Mapeamento", "Rótulo do registro:", initialvalue=f"{typ}@0x{base:X}")
            if not label: return
            template=self.profile["records"].get(typ,{"fields":[]})
            fields={}
            for f in template.get("fields",[]):
                fields[f["name"]]=dict(f)
            rec=MappedRecord(typ,base,label,fields,"USER-MAPPED")
            self.project.mapped_records.append(rec.to_dict())
            self.log(f"Registro {typ} mapeado em 0x{base:X}: {label}")
            self._refresh_records_tree()
            # select last
            children=self.tree_records.get_children()
            if children:
                self.tree_records.selection_set(children[-1]); self.on_record_select()
        except Exception as e:
            messagebox.showerror("Mapeamento",str(e))

    def add_custom_field(self):
        sel=self.tree_records.selection()
        if not sel:
            messagebox.showwarning("Campo", "Mapeie ou selecione um registro primeiro.")
            return
        idx=int(self.tree_records.item(sel[0],"tags")[0])
        rec=self.project.mapped_records[idx]
        name=simpledialog.askstring("Novo campo","Nome técnico do campo (ex: mp_cost):")
        if not name: return
        rel=simpledialog.askstring("Novo campo","Offset relativo (ex: 0x0A):",initialvalue="0x0")
        if rel is None:return
        dtype=simpledialog.askstring("Novo campo","Tipo: u8/u16le/u32le/s8/s16le/s32le/hex/str:shift_jis",initialvalue="u16le")
        if not dtype:return
        size_default={"u8":1,"s8":1,"u16le":2,"s16le":2,"u32le":4,"s32le":4}.get(dtype,1)
        size=simpledialog.askinteger("Novo campo","Tamanho em bytes:",initialvalue=size_default,minvalue=1,maxvalue=4096)
        if not size:return
        rec["fields"][name]={"name":name,"label":name,"rel_offset":parse_int(rel),"size":size,"dtype":dtype,"evidence":"USER-MAPPED"}
        self.log(f"Campo {name} definido em {rec['label']} +0x{parse_int(rel):X}")
        self.refresh_record_fields()

    def _refresh_records_tree(self):
        self.tree_records.delete(*self.tree_records.get_children())
        for i,rec in enumerate(self.project.mapped_records):
            item=self.tree_records.insert("",tk.END,values=(rec["record_type"],f"0x{rec['base_offset']:X}",rec["label"],rec.get("evidence","")),tags=(str(i),))

    def on_record_select(self,event=None):
        self.refresh_record_fields()

    def refresh_record_fields(self):
        self.tree_fields.delete(*self.tree_fields.get_children())
        if not self.source:return
        sel=self.tree_records.selection()
        if not sel:return
        idx=int(self.tree_records.item(sel[0],"tags")[0])
        rec=self.project.mapped_records[idx]
        for name,f in rec.get("fields",{}).items():
            rel=f.get("rel_offset")
            size=f.get("size",1)
            val="—"
            if rel is not None:
                try:
                    raw=self.source.bounded_slice(rec["base_offset"]+rel,size)
                    val=decode_scalar(raw,f.get("dtype","hex"))
                except Exception as e:
                    val=f"ERR: {e}"
            self.tree_fields.insert("",tk.END,values=(f.get("label",name),f"0x{rel:X}" if rel is not None else "?",f.get("dtype","hex"),val,f.get("evidence","UNKNOWN")),tags=(name,))

    def _get_selected_record_field(self):
        rsel=self.tree_records.selection(); fsel=self.tree_fields.selection()
        if not rsel or not fsel: return None
        ridx=int(self.tree_records.item(rsel[0],"tags")[0])
        name=self.tree_fields.item(fsel[0],"tags")[0]
        rec=self.project.mapped_records[ridx]
        return rec,name,rec["fields"][name]

    def edit_selected_field(self):
        if not self.require_source():return
        got=self._get_selected_record_field()
        if not got:
            messagebox.showwarning("Campo","Selecione um campo.");return
        rec,name,f=got
        rel=f.get("rel_offset")
        if rel is None:
            messagebox.showwarning("Campo","Defina primeiro o offset relativo deste campo.");return
        off=rec["base_offset"]+rel
        raw=self.source.bounded_slice(off,f["size"])
        current=decode_scalar(raw,f["dtype"])
        new=simpledialog.askstring("Editar campo",f"{rec['label']} / {f.get('label',name)}\nAtual: {current}\nNovo valor:",initialvalue=str(current))
        if new is None:return
        try:
            newb=encode_scalar(new,f["dtype"],f["size"])
            self.changeset.stage(off,newb,f"{rec['label']}.{name}",rec["record_type"],f.get("evidence","USER-MAPPED"))
            self.log(f"Alteração encenada: {rec['label']}.{name} @ 0x{off:X}")
            self._refresh_changes_tree();self.refresh_record_fields();self._refresh_dashboard()
        except Exception as e:
            messagebox.showerror("Edição",str(e))

    def field_to_hex(self):
        got=self._get_selected_record_field()
        if not got:return
        rec,name,f=got
        if f.get("rel_offset") is None:return
        self.notebook.select(self.tab_hex);self.goto_hex(rec["base_offset"]+f["rel_offset"])

    def remove_record(self):
        sel=self.tree_records.selection()
        if not sel:return
        idx=int(self.tree_records.item(sel[0],"tags")[0])
        if messagebox.askyesno("Remover","Remover este mapeamento do projeto? Não altera a ROM."):
            del self.project.mapped_records[idx];self._refresh_records_tree();self.tree_fields.delete(*self.tree_fields.get_children());self._refresh_dashboard()

    # ---------- graphics/appearance ----------
    def require_pillow(self):
        if Image is None:
            messagebox.showerror("Pillow","Este recurso requer Pillow. Execute o script instalar.sh ou instale 'Pillow'.")
            return False
        return True

    def scan_tim_assets(self):
        if not self.require_source() or not self.require_pillow():return
        try:
            self.tim_results=scan_tims(self.source.data)
            self.tree_tim.delete(*self.tree_tim.get_children())
            for i,info in enumerate(self.tim_results):
                self.tree_tim.insert("",tk.END,values=(f"0x{info.offset:X}",info.bpp,f"{info.width}x{info.height}","sim" if info.has_clut else "não"),tags=(str(i),))
            self.log(f"TIM scan: {len(self.tim_results)} candidato(s) válido(s).")
            self.lbl_graphics_status.config(text=f"{len(self.tim_results)} TIM(s) encontrados")
        except Exception as e:messagebox.showerror("TIM",str(e))

    def on_tim_select(self,event=None):
        sel=self.tree_tim.selection()
        if not sel or not self.source:return
        idx=int(self.tree_tim.item(sel[0],"tags")[0])
        try:
            im,info=decode_tim(self.source.data,self.tim_results[idx].offset)
            self.current_tim_image=im
            self.current_asset_image=im.copy()
            self.current_asset_path=f"TIM@0x{info.offset:X}"
            self.lbl_graphics_status.config(text=f"TIM 0x{info.offset:X} — {info.width}x{info.height} {info.bpp}bpp")
            self.render_actor_preview()
        except Exception as e:messagebox.showerror("TIM Preview",str(e))

    def export_current_tim(self):
        if not self.require_pillow() or self.current_tim_image is None:
            messagebox.showwarning("PNG","Selecione um TIM primeiro.");return
        path=filedialog.asksaveasfilename(defaultextension=".png",filetypes=[("PNG","*.png")])
        if path:
            self.current_tim_image.save(path,"PNG");self.log(f"TIM exportado para PNG: {path}")

    def import_preview_image(self):
        if not self.require_pillow():return
        path=filedialog.askopenfilename(filetypes=[("Imagens","*.png *.gif *.bmp *.jpg *.jpeg"),("Todos","*.*")])
        if not path:return
        try:
            im=Image.open(path).convert("RGBA")
            self.current_asset_image=im.copy();self.current_asset_path=path
            self.render_actor_preview();self.log(f"Imagem importada para preview: {path}")
        except Exception as e:messagebox.showerror("Imagem",str(e))

    def assign_direction_image(self):
        if not self.require_pillow() or self.current_asset_image is None:
            messagebox.showwarning("Preview","Selecione/importa uma imagem.");return
        d=self.direction_order[self.current_direction_index]
        # Persist a copy in memory; if external path exists, save path; TIM reference otherwise
        self.project.appearance.setdefault("directions",{})[d]=self.current_asset_path or "memory"
        setattr(self,f"_dir_image_{d}",self.current_asset_image.copy())
        self.log(f"Imagem atribuída à direção {d}.")
        self.render_actor_preview()

    def rotate_actor(self,delta):
        self.current_direction_index=(self.current_direction_index+delta)%len(self.direction_order)
        self.lbl_direction.config(text=f"Direção: {self.direction_order[self.current_direction_index]}")
        self.render_actor_preview()

    def add_animation_frame(self):
        if not self.require_pillow() or self.current_asset_image is None:
            messagebox.showwarning("Animação","Selecione/importa uma imagem.");return
        self.appearance_frames.append(self.current_asset_image.copy())
        self.appearance_frame_names.append(self.current_asset_path or f"frame{len(self.appearance_frames)}")
        self.project.appearance["animation"]=list(self.appearance_frame_names)
        self.log(f"Frame adicionado à animação ({len(self.appearance_frames)} total).")

    def clear_animation(self):
        self.stop_appearance();self.appearance_frames.clear();self.appearance_frame_names.clear();self.project.appearance["animation"]=[];self.log("Animação de preview limpa.")

    def play_appearance(self):
        if not self.appearance_frames:
            # fallback to direction spin if assigned
            frames=[]
            for d in self.direction_order:
                im=getattr(self,f"_dir_image_{d}",None)
                if im is not None:frames.append(im)
            if frames:self.appearance_frames=[im.copy() for im in frames]
        if not self.appearance_frames:
            messagebox.showwarning("Preview","Adicione frames ou atribua imagens às direções.");return
        self.stop_appearance();self.appearance_play_index=0
        self._appearance_tick()

    def _appearance_tick(self):
        if not self.appearance_frames:return
        self.current_asset_image=self.appearance_frames[self.appearance_play_index%len(self.appearance_frames)]
        self.render_actor_preview()
        self.appearance_play_index+=1
        self.appearance_play_job=self.root.after(180,self._appearance_tick)

    def stop_appearance(self):
        if self.appearance_play_job:
            try:self.root.after_cancel(self.appearance_play_job)
            except Exception:pass
            self.appearance_play_job=None

    def export_appearance_gif(self):
        if not self.require_pillow():return
        frames=self.appearance_frames[:]
        if not frames:
            frames=[getattr(self,f"_dir_image_{d}",None) for d in self.direction_order]
            frames=[x for x in frames if x is not None]
        if not frames:
            messagebox.showwarning("GIF","Não há frames para exportar.");return
        path=filedialog.asksaveasfilename(defaultextension=".gif",filetypes=[("GIF","*.gif")])
        if path:
            maxw=max(i.width for i in frames);maxh=max(i.height for i in frames)
            norm=[]
            for im in frames:
                canvas=Image.new("RGBA",(maxw,maxh),(0,0,0,0));canvas.alpha_composite(im,((maxw-im.width)//2,(maxh-im.height)//2));norm.append(canvas)
            norm[0].save(path,save_all=True,append_images=norm[1:],duration=180,loop=0,disposal=2)
            self.log(f"GIF exportado: {path}")

    def tint_current_asset(self):
        if not self.require_pillow() or self.current_asset_image is None:return
        rgb=colorchooser.askcolor(title="Cor de tint")[0]
        if not rgb:return
        r,g,b=[int(x) for x in rgb]
        src=self.current_asset_image.convert("RGBA")
        overlay=Image.new("RGBA",src.size,(r,g,b,90))
        out=Image.alpha_composite(src,overlay)
        # restore transparency mask from source
        out.putalpha(src.getchannel("A"))
        self.current_asset_image=out
        self.render_actor_preview();self.log("Tint aplicado ao preview (não grava ROM).")

    def render_actor_preview(self):
        if not hasattr(self,"canvas_actor"):return
        c=self.canvas_actor;c.delete("all")
        w=max(c.winfo_width(),420);h=max(c.winfo_height(),360)
        # pseudo-isometric battlefield ground
        cx,cy=w//2,h//2+70
        tile=42
        for y in range(-3,4):
            for x in range(-4,5):
                px=cx+(x-y)*tile//2;py=cy+(x+y)*tile//4
                pts=[px,py-tile//4,px+tile//2,py,px,py+tile//4,px-tile//2,py]
                c.create_polygon(pts,fill="#3d5948" if (x+y)%2==0 else "#465f50",outline="#24332a")
        d=self.direction_order[self.current_direction_index]
        im=getattr(self,f"_dir_image_{d}",None) or self.current_asset_image
        if im is not None and ImageTk is not None:
            scale=min(4.0,max(1.0,180/max(im.width,im.height)))
            disp=im.resize((max(1,int(im.width*scale)),max(1,int(im.height*scale))),Image.Resampling.NEAREST)
            self.current_tim_photo=ImageTk.PhotoImage(disp)
            c.create_image(cx,cy-70,image=self.current_tim_photo,anchor=tk.S)
        else:
            c.create_text(cx,cy-80,text="Selecione um TIM ou importe PNG",fill="white",font=("Segoe UI",14,"bold"))
        c.create_text(12,12,anchor=tk.NW,text=f"Direção {d} | Preview local — validação final deve ocorrer no emulador",fill="#d8e0e8",font=("Segoe UI",10,"bold"))

    # ---------- dialogue ----------
    def scan_strings(self):
        if not self.require_source():return
        enc=self.cmb_text_encoding.get();minchars=parse_int(self.spn_text_min.get(),5)
        data=self.source.data
        results=[]
        if enc=="ascii":
            rx = __import__('re').compile(rb"[\x20-\x7E]{%d,}"%minchars)
            for m in rx.finditer(data):results.append({"offset":m.start(),"length":len(m.group()),"text":m.group().decode('ascii')})
        else:
            # conservative Shift-JIS scanner: printable ASCII and 2-byte SJIS pairs, terminated by control/invalid byte
            i=0
            while i<len(data):
                start=i;buf=bytearray();chars=0
                while i<len(data):
                    b=data[i]
                    if 0x20<=b<=0x7E or 0xA1<=b<=0xDF:
                        buf.append(b);i+=1;chars+=1;continue
                    if (0x81<=b<=0x9F or 0xE0<=b<=0xFC) and i+1<len(data) and (0x40<=data[i+1]<=0xFC and data[i+1]!=0x7F):
                        buf.extend(data[i:i+2]);i+=2;chars+=1;continue
                    break
                if chars>=minchars:
                    try:text=bytes(buf).decode('shift_jis')
                    except Exception:text=""
                    if text.strip():results.append({"offset":start,"length":len(buf),"text":text})
                i=max(i+1,start+1)
                if len(results)>=20000:break
        self.dialogue_results=results
        self.tree_text.delete(*self.tree_text.get_children())
        for idx,r in enumerate(results[:10000]):
            self.tree_text.insert("",tk.END,values=(f"0x{r['offset']:X}",r['length'],r['text'].replace('\n',' ')[:100]),tags=(str(idx),))
        self.log(f"Text scan ({enc}): {len(results)} string(s) candidata(s).")

    def on_text_select(self,event=None):
        sel=self.tree_text.selection()
        if not sel:return
        idx=int(self.tree_text.item(sel[0],"tags")[0]);r=self.dialogue_results[idx]
        self.txt_dialogue_edit.delete("1.0",tk.END);self.txt_dialogue_edit.insert("1.0",r['text'])
        self.render_dialogue_preview()

    def import_portrait(self):
        if not self.require_pillow():return
        path=filedialog.askopenfilename(filetypes=[("Imagens","*.png *.gif *.bmp *.jpg *.jpeg"),("Todos","*.*")])
        if not path:return
        self.portrait_image=Image.open(path).convert("RGBA");self.render_dialogue_preview();self.log(f"Retrato importado: {path}")

    def render_dialogue_preview(self):
        if not hasattr(self,"canvas_dialogue"):return
        c=self.canvas_dialogue;c.delete("all")
        w=max(c.winfo_width(),500);h=max(c.winfo_height(),300)
        c.create_rectangle(12,h-155,w-12,h-14,fill="#10131a",outline="#d8d8d8",width=2)
        x0=26
        if self.portrait_image is not None and ImageTk is not None:
            im=self.portrait_image.copy();im.thumbnail((110,110),Image.Resampling.NEAREST)
            self.portrait_photo=ImageTk.PhotoImage(im)
            c.create_image(28,h-142,anchor=tk.NW,image=self.portrait_photo);x0=155
        speaker=self.ent_speaker.get().strip() if hasattr(self,"ent_speaker") else ""
        text=self.txt_dialogue_edit.get("1.0",tk.END).strip() if hasattr(self,"txt_dialogue_edit") else ""
        c.create_text(x0,h-140,anchor=tk.NW,text=speaker,fill="#f5d873",font=("Segoe UI",11,"bold"))
        c.create_text(x0,h-112,anchor=tk.NW,text=text,fill="white",font=("Segoe UI",12),width=max(100,w-x0-35))
        c.create_text(12,12,anchor=tk.NW,text="Preview tipográfico aproximado — largura final deve ser validada no jogo.",fill="#cbd5e1")

    def _selected_dialogue(self):
        sel=self.tree_text.selection()
        if not sel:return None
        idx=int(self.tree_text.item(sel[0],"tags")[0]);return self.dialogue_results[idx]

    def stage_dialogue_edit(self):
        if not self.require_source():return
        r=self._selected_dialogue()
        if not r:
            messagebox.showwarning("Fala","Selecione uma string detectada.");return
        enc=self.cmb_text_encoding.get();text=self.txt_dialogue_edit.get("1.0",tk.END).rstrip("\n")
        try:
            raw=text.encode(enc)
            if len(raw)>r['length']:
                raise ValueError(f"Texto novo ocupa {len(raw)} bytes; espaço original possui {r['length']}. Relocação de string não está mapeada, portanto a operação foi bloqueada.")
            newb=raw+b"\x00"*(r['length']-len(raw))
            self.changeset.stage(r['offset'],newb,f"Texto @0x{r['offset']:X}","dialogue","USER-MAPPED")
            self._refresh_changes_tree();self._refresh_dashboard();self.log(f"Substituição de texto encenada em 0x{r['offset']:X}.")
        except Exception as e:messagebox.showerror("Fala",str(e))

    def dialogue_to_hex(self):
        r=self._selected_dialogue()
        if r:self.notebook.select(self.tab_hex);self.goto_hex(r['offset'])

    # ---------- scene preview ----------
    def set_scene_tool(self,tool):
        self.scene_tool=tool;self.log(f"Scene tool: {tool}")

    def scene_grid_geometry(self):
        st=self.project.scene
        return int(st.get("width",12)),int(st.get("height",10))

    def on_scene_click(self,event):
        cols,rows=self.scene_grid_geometry();ts=self.scene_tile_size
        ox=max(20,(self.canvas_scene.winfo_width()-cols*ts)//2);oy=40
        x=(event.x-ox)//ts;y=(event.y-oy)//ts
        if not (0<=x<cols and 0<=y<rows):return
        key=f"{x},{y}"
        if self.scene_tool=="terrain":
            self.project.scene.setdefault("tiles",{})[key]=self.cmb_terrain.get()
        elif self.scene_tool=="unit":
            name=simpledialog.askstring("Unidade","Nome/rótulo da unidade:",initialvalue="Ash")
            if name:
                self.project.scene.setdefault("units",[]).append({"x":x,"y":y,"name":name})
        else:
            text=simpledialog.askstring("Evento/Fala","Texto do evento:",initialvalue="Fala da cena")
            if text:self.project.scene.setdefault("events",[]).append({"x":x,"y":y,"text":text})
        self.render_scene()

    def render_scene(self):
        if not hasattr(self,"canvas_scene"):return
        c=self.canvas_scene;c.delete("all")
        cols,rows=self.scene_grid_geometry();ts=self.scene_tile_size
        ox=max(20,(c.winfo_width()-cols*ts)//2);oy=40
        colors={"grass":"#496b4c","stone":"#676b70","water":"#386c91","wall":"#6b5442"}
        tiles=self.project.scene.get("tiles",{})
        for y in range(rows):
            for x in range(cols):
                terrain=tiles.get(f"{x},{y}","grass")
                c.create_rectangle(ox+x*ts,oy+y*ts,ox+(x+1)*ts,oy+(y+1)*ts,fill=colors.get(terrain,"#496b4c"),outline="#1c2833")
                c.create_text(ox+x*ts+4,oy+y*ts+4,anchor=tk.NW,text=f"{x},{y}",fill="#dbe4ea",font=("Consolas",7))
        for u in self.project.scene.get("units",[]):
            px=ox+u['x']*ts+ts//2;py=oy+u['y']*ts+ts//2
            c.create_oval(px-12,py-12,px+12,py+12,fill="#f1c75b",outline="black")
            c.create_text(px,py+19,text=u['name'],fill="white",font=("Segoe UI",8,"bold"))
        for ev in self.project.scene.get("events",[]):
            px=ox+ev['x']*ts+ts//2;py=oy+ev['y']*ts+ts//2
            c.create_rectangle(px-7,py-7,px+7,py+7,fill="#c95d63",outline="white")
        c.create_text(10,10,anchor=tk.NW,text=f"Tool={self.scene_tool} | Clique no grid para editar preview local",fill="white",font=("Segoe UI",10,"bold"))

    def clear_scene(self):
        if messagebox.askyesno("Cena","Limpar tiles, unidades e eventos do preview?"):
            self.project.scene={"width":12,"height":10,"tiles":{},"units":[],"events":[]};self.render_scene();self.log("Scene preview limpo.")

    def save_scene_state(self,silent=False):
        # state is already live in project; this action exists to make user intent explicit
        if not silent:
            self.log("Scene preview incorporado ao estado do projeto.");messagebox.showinfo("Cena","Cena salva no projeto. Use Ctrl+S para gravar o arquivo do projeto.")

    def scene_play_preview(self):
        units=self.project.scene.get("units",[]);events=self.project.scene.get("events",[])
        if not units and not events:
            messagebox.showwarning("Preview","Adicione ao menos uma unidade ou evento.");return
        # sequence through events with visual highlight, no fake ROM execution
        self._scene_preview_step(0)

    def _scene_preview_step(self,index):
        events=self.project.scene.get("events",[])
        self.render_scene()
        if not events:return
        ev=events[index%len(events)]
        cols,rows=self.scene_grid_geometry();ts=self.scene_tile_size;ox=max(20,(self.canvas_scene.winfo_width()-cols*ts)//2);oy=40
        px=ox+ev['x']*ts+ts//2;py=oy+ev['y']*ts+ts//2
        self.canvas_scene.create_oval(px-17,py-17,px+17,py+17,outline="#ffffff",width=3,tags="eventfocus")
        self.canvas_scene.create_rectangle(20,self.canvas_scene.winfo_height()-100,self.canvas_scene.winfo_width()-20,self.canvas_scene.winfo_height()-20,fill="#111",outline="#ddd")
        self.canvas_scene.create_text(35,self.canvas_scene.winfo_height()-85,anchor=tk.NW,text=ev['text'],fill="white",width=max(100,self.canvas_scene.winfo_width()-80),font=("Segoe UI",11))
        if index+1<len(events):self.root.after(1200,lambda:self._scene_preview_step(index+1))

    # ---------- changes/build ----------
    def _refresh_changes_tree(self):
        self.tree_changes.delete(*self.tree_changes.get_children())
        if not self.changeset:return
        for i,c in enumerate(self.changeset.changes):
            self.tree_changes.insert("",tk.END,values=("✓" if c.enabled else "—",f"0x{c.offset:X}",c.label,c.category,c.old_hex,c.new_hex,c.evidence),tags=(str(i),))

    def toggle_change(self):
        if not self.changeset:return
        sel=self.tree_changes.selection()
        if not sel:return
        idx=int(self.tree_changes.item(sel[0],"tags")[0]);self.changeset.toggle(idx);self._refresh_changes_tree();self._refresh_dashboard()

    def remove_change(self):
        if not self.changeset:return
        sel=self.tree_changes.selection()
        if not sel:return
        idx=int(self.tree_changes.item(sel[0],"tags")[0]);self.changeset.remove(idx);self._refresh_changes_tree();self._refresh_dashboard()

    def undo(self):
        if self.changeset and self.changeset.undo():
            self.log("Undo aplicado ao ChangeSet.");self._refresh_changes_tree();self._refresh_dashboard()
        else:self.root.bell()

    def redo(self):
        if self.changeset and self.changeset.redo():
            self.log("Redo aplicado ao ChangeSet.");self._refresh_changes_tree();self._refresh_dashboard()
        else:self.root.bell()

    def validate_changes(self):
        if not self.changeset:
            messagebox.showwarning("Validação","Nenhuma fonte/ChangeSet ativo.");return False
        errors=self.changeset.validate()
        if errors:
            messagebox.showerror("Validação","FAIL\n\n"+"\n".join(errors));self.log(f"Validação: FAIL ({len(errors)} erro(s))");return False
        messagebox.showinfo("Validação",f"PASS\n\n{sum(1 for c in self.changeset.changes if c.enabled)} alteração(ões) habilitada(s).\nOriginal permanece intacto.")
        self.log("Validação do ChangeSet: PASS");return True

    def build_test_copy(self):
        if not self.require_source() or not self.changeset:return
        if not self.changeset.changes:
            messagebox.showwarning("Build","Não há alterações.");return
        if self.changeset.validate():
            self.validate_changes();return
        stem=self.source.path.stem+"-TEST"+self.source.path.suffix
        path=filedialog.asksaveasfilename(initialfile=stem,defaultextension=self.source.path.suffix or ".bin")
        if not path:return
        try:
            self.changeset.build_copy(path)
            self.log(f"Cópia de teste construída: {path}")
            messagebox.showinfo("Build",f"Cópia de teste criada.\n\nOriginal NÃO foi modificado.\n\n{path}")
        except Exception as e:messagebox.showerror("Build",str(e))

    def export_ips(self):
        if not self.require_source() or not self.changeset:return
        path=filedialog.asksaveasfilename(defaultextension=".ips",filetypes=[("IPS","*.ips")])
        if not path:return
        try:
            self.changeset.export_ips(path);self.log(f"Patch IPS exportado: {path}");messagebox.showinfo("IPS",f"Patch exportado:\n{path}")
        except Exception as e:messagebox.showerror("IPS",str(e))

    def export_manifest(self):
        if not self.changeset:return
        path=filedialog.asksaveasfilename(defaultextension=".json",filetypes=[("JSON","*.json")])
        if not path:return
        data={"project":self.project.name,"source":str(self.source.path) if self.source else "","sha256":self.source.sha256 if self.source else "","changes":[asdict(c) for c in self.changeset.changes]}
        Path(path).write_text(json.dumps(data,indent=2,ensure_ascii=False),encoding="utf-8");self.log(f"Manifesto exportado: {path}")

    # ---------- refresh/log ----------
    def _refresh_all(self):
        self._refresh_dashboard();self._refresh_records_tree();self._refresh_changes_tree();self.render_scene();self.render_actor_preview();self.render_dialogue_preview()

    def _refresh_dashboard(self):
        if not hasattr(self,"lbl_card_source"):return
        if self.source:
            self.lbl_card_source.config(text=f"{self.source.path.name}\n{human_size(self.source.size)}")
            self.lbl_card_hash.config(text=self.source.sha256[:16]+"…")
            self.lbl_top_status.config(text="● FONTE OK / ORIGINAL READ-ONLY")
        else:
            self.lbl_card_source.config(text="Nenhuma");self.lbl_card_hash.config(text="—");self.lbl_top_status.config(text="● SEM FONTE")
        n=len(self.changeset.changes) if self.changeset else 0
        self.lbl_card_changes.config(text=str(n));self.lbl_card_records.config(text=str(len(self.project.mapped_records)))
        if hasattr(self,"txt_dashboard"):
            lines=[f"Projeto: {self.project.name}",f"Arquivo de projeto: {self.project_path or 'ainda não salvo'}",""]
            if self.source:
                lines += [f"Fonte: {self.source.path}",f"Tamanho: {human_size(self.source.size)}",f"SHA-256: {self.source.sha256}",f"PS-X EXE: {'SIM' if self.source.is_psx_exe else 'NÃO/ARQUIVO GENÉRICO'}"]
                if self.source.is_psx_exe:lines.append(f"RAM destination: 0x{self.source.ram_destination:08X}")
            lines += ["",f"Mapeamentos: {len(self.project.mapped_records)}",f"Alterações encenadas: {n}","", "Política de segurança:","  • fonte original é somente leitura", "  • edições ficam em ChangeSet", "  • build gera uma cópia separada", "  • offsets não comprovados são rotulados como hipótese/user-mapped"]
            self.txt_dashboard.config(state="normal");self.txt_dashboard.delete("1.0",tk.END);self.txt_dashboard.insert("1.0","\n".join(lines));self.txt_dashboard.config(state="disabled")

    def log(self,msg):
        if not hasattr(self,"txt_log"):return
        self.txt_log.config(state="normal");self.txt_log.insert(tk.END,"• "+msg+"\n");self.txt_log.see(tk.END);self.txt_log.config(state="disabled")


def main():
    root=tk.Tk()
    app=VH2StudioApp(root)
    root.mainloop()


if __name__=="__main__":
    main()
