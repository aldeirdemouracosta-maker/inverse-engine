#!/usr/bin/env python3
"""
VH2 ROM Editor GUI — Engenharia Reversa + Edição + Patch para Vandal Hearts II (PS1)
Interface gráfica simples, funcional e intuitiva construída com Tkinter.
"""
import json
import struct
import hashlib
import shutil
import re
from pathlib import Path
from enum import Enum
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
CONFIG_DIR = Path.home() / ".config" / "vh2rom"
CONFIG_FILE = CONFIG_DIR / "items.json"
KNOWN_ROMS_FILE = CONFIG_DIR / "known_roms.json"
PSEXE_HEADER_SIZE = 0x800
PSEXE_MAGIC = b"PS-X EXE"
class ItemField(Enum):
    """Layout relativo da struct do item no PS1"""
    ID = ("id", 0, 2, "u16le")
    NAME = ("name", 2, 8, "str")
    ATTACK = ("attack", 10, 2, "u16le")
    DEFENSE = ("defense", 12, 2, "u16le")
    TYPE = ("type", 14, 1, "u8")
    RARITY = ("rarity", 15, 1, "u8")
    SPRITE_OFFSET = ("sprite_offset", 16, 4, "u32le")
    DESCRIPTION = ("description", 20, 2, "u16le")
    def __init__(self, field_name, rel_offset, size, dtype):
        self.field_name = field_name
        self.rel_offset = rel_offset
        self.size = size
        self.dtype = dtype
def parse_int(s, default=None):
    if s is None:
        return default
    s = str(s).strip()
    if s == "":
        return default
    try:
        return int(s, 0)
    except ValueError:
        try:
            return int(s)
        except ValueError:
            raise ValueError(f"Valor inválido: '{s}'")
class CustomTextDecoder:
    def __init__(self, tbl_path: str = None):
        self.char_to_byte = {}
        self.byte_to_char = {}
        if tbl_path and Path(tbl_path).exists():
            self.load_tbl(tbl_path)
    def load_tbl(self, tbl_path: str):
        with open(tbl_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith(";"):
                    continue
                if "=" in line:
                    hex_val, char_val = line.split("=", 1)
                    val = int(hex_val, 16)
                    self.byte_to_char[val] = char_val
                    self.char_to_byte[char_val] = val
    def decode_bytes(self, raw_bytes: bytes, encoding="shift_jis") -> str:
        if self.byte_to_char:
            res = []
            i = 0
            while i < len(raw_bytes):
                if i + 1 < len(raw_bytes):
                    two_bytes = (raw_bytes[i] << 8) | raw_bytes[i + 1]
                    if two_bytes in self.byte_to_char:
                        res.append(self.byte_to_char[two_bytes])
                        i += 2
                        continue
                one_byte = raw_bytes[i]
                if one_byte in self.byte_to_char:
                    res.append(self.byte_to_char[one_byte])
                elif one_byte == 0x00:
                    res.append("[END]")
                    break
                else:
                    res.append(f"\\x{one_byte:02X}")
                i += 1
            return "".join(res)
        else:
            null_idx = raw_bytes.find(b"\x00")
            if null_idx != -1:
                raw_bytes = raw_bytes[:null_idx]
            try:
                return raw_bytes.decode(encoding, errors="replace")
            except Exception:
                return raw_bytes.hex()
class ROMScanner:
    def __init__(self, rom_path: str):
        self.rom_path = Path(rom_path)
        self.data = self.rom_path.read_bytes()
        self.hash = hashlib.sha256(self.data).hexdigest()
        if self.data[:8] == PSEXE_MAGIC:
            self.has_psexe_header = True
            self.ram_base_offset = PSEXE_HEADER_SIZE
            self.ram_destination = struct.unpack("<I", self.data[0x18:0x1C])[0]
        else:
            self.has_psexe_header = False
            self.ram_base_offset = 0
            self.ram_destination = 0x80010000
    def scan_value(self, value: int, datatype: str = "u16le") -> list:
        if datatype == "u16le":
            pattern = struct.pack("<H", value)
        elif datatype == "u32le":
            pattern = struct.pack("<I", value)
        elif datatype == "u8":
            pattern = struct.pack("B", value)
        else:
            return []
        results = []
        pos = 0
        while True:
            pos = self.data.find(pattern, pos)
            if pos == -1:
                break
            results.append(pos)
            pos += 1
        return results
    def scan_bytes_regex(self, hex_pattern: str) -> list:
        tokens = hex_pattern.strip().split()
        regex_parts = []
        for tok in tokens:
            if tok in ("??", "?"):
                regex_parts.append(b".")
            else:
                regex_parts.append(re.escape(bytes([int(tok, 16)])))
        regex = re.compile(b"".join(regex_parts), re.DOTALL)
        return [match.start() for match in regex.finditer(self.data)]
    def ram_to_file(self, ram_addr) -> int:
        ram_int = parse_int(ram_addr) if isinstance(ram_addr, str) else ram_addr
        return ram_int - self.ram_destination + self.ram_base_offset
    def file_to_ram(self, file_offset) -> int:
        offset_int = parse_int(file_offset) if isinstance(file_offset, str) else file_offset
        return offset_int - self.ram_base_offset + self.ram_destination
class ItemDatabase:
    def __init__(self):
        self.items = {}
        self.load()
    def load(self):
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, "r") as f:
                    data = json.load(f)
                for item_id, item_data in data.items():
                    self.items[int(item_id)] = item_data
            except Exception as e:
                print(f"Erro ao carregar banco de dados: {e}")
    def save(self):
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        if CONFIG_FILE.exists():
            shutil.copy2(CONFIG_FILE, CONFIG_FILE.with_suffix(".json.bak"))
        with open(CONFIG_FILE, "w") as f:
            json.dump({str(k): v for k, v in self.items.items()}, f, indent=2)
class PatchManager:
    def __init__(self, scanner: ROMScanner):
        self.scanner = scanner
        self.changes = {}  # {offset: (old_bytes, new_bytes, item_id, field_name)}
    def register_change(self, offset: int, new_bytes: bytes, item_id: int, field_name: str):
        old_bytes = self.scanner.data[offset:offset + len(new_bytes)]
        self.changes[offset] = (old_bytes, new_bytes, item_id, field_name)
    def generate_ips(self, output_path: str):
        if not self.changes:
            return False
        ips_data = b"PATCH"
        for offset in sorted(self.changes.keys()):
            _, new_bytes, _, _ = self.changes[offset]
            ips_data += offset.to_bytes(3, "big")
            ips_data += len(new_bytes).to_bytes(2, "big")
            ips_data += new_bytes
        ips_data += b"EOF"
        Path(output_path).write_bytes(ips_data)
        return True
class VH2EditorGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("VH2 ROM Editor — Engenharia Reversa PS1")
        self.root.geometry("980x680")
        self.root.minsize(800, 550)
        self.db = ItemDatabase()
        self.scanner = None
        self.patcher = None
        self.decoder = CustomTextDecoder()
        self._build_style()
        self._build_ui()
    def _build_style(self):
        self.style = ttk.Style()
        self.style.theme_use("clam")
        self.style.configure("TButton", font=("Segoe UI", 9, "bold"), padding=6)
        self.style.configure("Accent.TButton", background="#2b6cb0", foreground="white")
        self.style.map("Accent.TButton", background=[("active", "#2c5282")])
        self.style.configure("Success.TButton", background="#2f855a", foreground="white")
        self.style.map("Success.TButton", background=[("active", "#22543d")])
    def _build_ui(self):
        # Header / Barra de Status Superior
        top_frame = ttk.Frame(self.root, padding=10)
        top_frame.pack(fill=tk.X)
        btn_load = ttk.Button(top_frame, text="📁 Abrir ROM PS1", style="Accent.TButton", command=self.load_rom)
        btn_load.pack(side=tk.LEFT, padx=5)
        self.lbl_rom_info = ttk.Label(top_frame, text="Nenhuma ROM carregada", font=("Segoe UI", 10, "italic"))
        self.lbl_rom_info.pack(side=tk.LEFT, padx=15)
        # Notebook (Abas)
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        # Aba 1: Scan & Mapeamento
        self.tab_scan = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(self.tab_scan, text="🔍 Scan & Mapeamento")
        self._build_tab_scan()
        # Aba 2: Editor de Itens
        self.tab_edit = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(self.tab_edit, text="✏️ Editor de Itens")
        self._build_tab_edit()
        # Aba 3: Patch IPS
        self.tab_patch = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(self.tab_patch, text="🧩 Patch IPS")
        self._build_tab_patch()
        # Console de Log Inferior
        log_frame = ttk.LabelFrame(self.root, text=" Console de Operações ", padding=5)
        log_frame.pack(fill=tk.X, padx=10, pady=5)
        self.txt_log = scrolledtext.ScrolledText(log_frame, height=6, state="disabled", font=("Consolas", 9))
        self.txt_log.pack(fill=tk.BOTH, expand=True)
        self.log("Aplicação iniciada. Carregue uma ROM da SLUS para começar.")
    def _build_tab_scan(self):
        ctrl_frame = ttk.LabelFrame(self.tab_scan, text=" Ferramentas de Busca ", padding=10)
        ctrl_frame.pack(fill=tk.X)
        # Fileira 1: Scan Valor
        ttk.Label(ctrl_frame, text="Valor Hex/Dec:").grid(row=0, column=0, sticky=tk.W, padx=2)
        self.ent_scan_val = ttk.Entry(ctrl_frame, width=15)
        self.ent_scan_val.grid(row=0, column=1, padx=5)
        ttk.Label(ctrl_frame, text="Tipo:").grid(row=0, column=2, padx=2)
        self.cmb_dtype = ttk.Combobox(ctrl_frame, values=["u16le", "u32le", "u8"], width=8, state="readonly")
        self.cmb_dtype.set("u16le")
        self.cmb_dtype.grid(row=0, column=3, padx=5)
        btn_search_val = ttk.Button(ctrl_frame, text="🔍 Buscar Valor", command=self.action_scan_value)
        btn_search_val.grid(row=0, column=4, padx=5)
        # Fileira 2: Scan Bytes Wildcard
        ttk.Label(ctrl_frame, text="Bytes Wildcard:").grid(row=1, column=0, sticky=tk.W, padx=2, pady=5)
        self.ent_scan_bytes = ttk.Entry(ctrl_frame, width=30)
        self.ent_scan_bytes.insert(0, "B6 ?? 00")
        self.ent_scan_bytes.grid(row=1, column=1, columnspan=3, sticky=tk.EW, padx=5, pady=5)
        btn_search_bytes = ttk.Button(ctrl_frame, text="🧩 Buscar Padrão", command=self.action_scan_bytes)
        btn_search_bytes.grid(row=1, column=4, padx=5, pady=5)
        # Tabela de Resultados do Scan
        table_frame = ttk.LabelFrame(self.tab_scan, text=" Resultados Encontrados ", padding=5)
        table_frame.pack(fill=tk.BOTH, expand=True, pady=10)
        cols = ("file_offset", "ram_offset", "hex_preview")
        self.tree_scan = ttk.Treeview(table_frame, columns=cols, show="headings")
        self.tree_scan.heading("file_offset", text="Offset Arquivo (SLUS)")
        self.tree_scan.heading("ram_offset", text="Endereço RAM PS1")
        self.tree_scan.heading("hex_preview", text="Preview Hexadecimal")
        self.tree_scan.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)
        sb = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.tree_scan.yview)
        self.tree_scan.configure(yscroll=sb.set)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        # Ação para mapear item
        map_frame = ttk.Frame(self.tab_scan)
        map_frame.pack(fill=tk.X)
        btn_map = ttk.Button(map_frame, text="📌 Mapear Offset Selecionado como Item", style="Success.TButton", command=self.action_map_item)
        btn_map.pack(side=tk.RIGHT, padx=5)
    def _build_tab_edit(self):
        # Mapeamento do Treeview de Itens
        table_frame = ttk.LabelFrame(self.tab_edit, text=" Itens Mapeados ", padding=5)
        table_frame.pack(fill=tk.BOTH, expand=True)
        cols = ("id", "slus", "ram", "attack", "defense", "type", "name")
        self.tree_items = ttk.Treeview(table_frame, columns=cols, show="headings")
        self.tree_items.heading("id", text="ID (Hex)")
        self.tree_items.heading("slus", text="Offset File")
        self.tree_items.heading("ram", text="RAM Addr")
        self.tree_items.heading("attack", text="Ataque")
        self.tree_items.heading("defense", text="Defesa")
        self.tree_items.heading("type", text="Tipo")
        self.tree_items.heading("name", text="Nome Extraído")
        self.tree_items.column("id", width=80)
        self.tree_items.column("slus", width=100)
        self.tree_items.column("ram", width=110)
        self.tree_items.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)
        sb = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.tree_items.yview)
        self.tree_items.configure(yscroll=sb.set)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        # Painel de Edição Direta
        edit_panel = ttk.LabelFrame(self.tab_edit, text=" Painel de Edição de Atributos ", padding=10)
        edit_panel.pack(fill=tk.X, pady=10)
        ttk.Label(edit_panel, text="Ataque:").grid(row=0, column=0, padx=5, pady=5)
        self.ent_edit_atk = ttk.Entry(edit_panel, width=10)
        self.ent_edit_atk.grid(row=0, column=1, padx=5, pady=5)
        ttk.Label(edit_panel, text="Defesa:").grid(row=0, column=2, padx=5, pady=5)
        self.ent_edit_def = ttk.Entry(edit_panel, width=10)
        self.ent_edit_def.grid(row=0, column=3, padx=5, pady=5)
        btn_apply = ttk.Button(edit_panel, text="💾 Aplicar Edição na Memória", style="Success.TButton", command=self.action_apply_edit)
        btn_apply.grid(row=0, column=4, padx=15, pady=5)
        self.tree_items.bind("<<TreeviewSelect>>", self._on_item_select)
    def _build_tab_patch(self):
        # Tabela de Edições Pendentes
        table_frame = ttk.LabelFrame(self.tab_patch, text=" Edições Pendentes (Memória Interna) ", padding=5)
        table_frame.pack(fill=tk.BOTH, expand=True)
        cols = ("offset", "item_id", "field", "old_val", "new_val")
        self.tree_patch = ttk.Treeview(table_frame, columns=cols, show="headings")
        self.tree_patch.heading("offset", text="Offset Arquivo")
        self.tree_patch.heading("item_id", text="Item ID")
        self.tree_patch.heading("field", text="Campo")
        self.tree_patch.heading("old_val", text="Bytes Antigos")
        self.tree_patch.heading("new_val", text="Bytes Novos")
        self.tree_patch.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)
        sb = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.tree_patch.yview)
        self.tree_patch.configure(yscroll=sb.set)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        # Botões de Ação
        btn_frame = ttk.Frame(self.tab_patch, padding=10)
        btn_frame.pack(fill=tk.X)
        btn_export = ttk.Button(btn_frame, text="🧩 Exportar Patch IPS...", style="Success.TButton", command=self.action_export_ips)
        btn_export.pack(side=tk.RIGHT, padx=5)
    def log(self, msg: str):
        self.txt_log.config(state="normal")
        self.txt_log.insert(tk.END, f"• {msg}\n")
        self.txt_log.see(tk.END)
        self.txt_log.config(state="disabled")
    def load_rom(self):
        path = filedialog.askopenfilename(filetypes=[("Arquivos PS1", "*.BIN *.iso *.SLUS*"), ("Todos os Arquivos", "*.*")])
        if not path:
            return
        try:
            self.scanner = ROMScanner(path)
            self.patcher = PatchManager(self.scanner)
            self.lbl_rom_info.config(
                text=f"ROM: {self.scanner.rom_path.name} | SHA256: {self.scanner.hash[:12]}... | RAM Base: 0x{self.scanner.ram_destination:08X}",
                font=("Segoe UI", 9, "bold")
            )
            self.log(f"ROM carregada com sucesso: {path}")
            self._refresh_items_tree()
        except Exception as e:
            messagebox.showerror("Erro ao carregar ROM", str(e))
    def action_scan_value(self):
        if not self.scanner:
            messagebox.showwarning("Aviso", "Carregue uma ROM primeiro.")
            return
        val_str = self.ent_scan_val.get()
        val = parse_int(val_str)
        if val is None:
            messagebox.showerror("Erro", "Insira um valor válido.")
            return
        dtype = self.cmb_dtype.get()
        results = self.scanner.scan_value(val, dtype)
        self.tree_scan.delete(*self.tree_scan.get_children())
        for pos in results[:100]:
            ram_addr = self.scanner.file_to_ram(pos)
            preview = self.scanner.data[pos:pos+8].hex().upper()
            self.tree_scan.insert("", tk.END, values=(f"0x{pos:06X}", f"0x{ram_addr:08X}", preview))
        self.log(f"Scan de valor '{val_str}' encontrou {len(results)} ocorrência(s).")
    def action_scan_bytes(self):
        if not self.scanner:
            messagebox.showwarning("Aviso", "Carregue uma ROM primeiro.")
            return
        pattern = self.ent_scan_bytes.get()
        try:
            results = self.scanner.scan_bytes_regex(pattern)
            self.tree_scan.delete(*self.tree_scan.get_children())
            for pos in results[:100]:
                ram_addr = self.scanner.file_to_ram(pos)
                preview = self.scanner.data[pos:pos+8].hex().upper()
                self.tree_scan.insert("", tk.END, values=(f"0x{pos:06X}", f"0x{ram_addr:08X}", preview))
            self.log(f"Scan de bytes '{pattern}' encontrou {len(results)} ocorrência(s).")
        except Exception as e:
            messagebox.showerror("Erro no Padrão", str(e))
    def action_map_item(self):
        selected = self.tree_scan.selection()
        if not selected:
            messagebox.showwarning("Aviso", "Selecione uma linha dos resultados do scan.")
            return
        item_values = self.tree_scan.item(selected[0], "values")
        file_offset = parse_int(item_values[0])
        ram_offset = item_values[1]
        # Extrai os dados automáticos da struct
        raw_id = struct.unpack("<H", self.scanner.data[file_offset:file_offset+2])[0]
        atk = struct.unpack("<H", self.scanner.data[file_offset+10:file_offset+12])[0]
        defe = struct.unpack("<H", self.scanner.data[file_offset+12:file_offset+14])[0]
        itype = self.scanner.data[file_offset+14]
        name_raw = self.scanner.data[file_offset+2:file_offset+10]
        name_str = self.decoder.decode_bytes(name_raw)
        item_data = {
            "item_id": raw_id,
            "record_slus": f"0x{file_offset:X}",
            "record_ram": ram_offset,
            "attack": atk,
            "defense": defe,
            "type": itype,
            "name": name_str
        }
        self.db.items[raw_id] = item_data
        self.db.save()
        self._refresh_items_tree()
        self.log(f"Item 0x{raw_id:X} mapeado em {item_data['record_slus']}.")
        self.notebook.select(self.tab_edit)
    def _refresh_items_tree(self):
        self.tree_items.delete(*self.tree_items.get_children())
        for item_id, data in sorted(self.db.items.items()):
            self.tree_items.insert("", tk.END, values=(
                f"0x{item_id:04X}",
                data.get("record_slus"),
                data.get("record_ram"),
                data.get("attack", 0),
                data.get("defense", 0),
                data.get("type", 0),
                data.get("name", "N/A")
            ))
    def _on_item_select(self, event):
        selected = self.tree_items.selection()
        if not selected:
            return
        vals = self.tree_items.item(selected[0], "values")
        self.ent_edit_atk.delete(0, tk.END)
        self.ent_edit_atk.insert(0, vals[3])
        self.ent_edit_def.delete(0, tk.END)
        self.ent_edit_def.insert(0, vals[4])
    def action_apply_edit(self):
        selected = self.tree_items.selection()
        if not selected or not self.patcher:
            messagebox.showwarning("Aviso", "Selecione um item para editar.")
            return
        vals = self.tree_items.item(selected[0], "values")
        item_id = parse_int(vals[0])
        file_offset = parse_int(vals[1])
        new_atk = parse_int(self.ent_edit_atk.get())
        new_def = parse_int(self.ent_edit_def.get())
        # Registra alterações nos offsets de Ataque (+10) e Defesa (+12)
        atk_bytes = struct.pack("<H", new_atk)
        def_bytes = struct.pack("<H", new_def)
        self.patcher.register_change(file_offset + 10, atk_bytes, item_id, "attack")
        self.patcher.register_change(file_offset + 12, def_bytes, item_id, "defense")
        # Atualiza o banco local
        if item_id in self.db.items:
            self.db.items[item_id]["attack"] = new_atk
            self.db.items[item_id]["defense"] = new_def
            self.db.save()
        self._refresh_items_tree()
        self._refresh_patch_tree()
        self.log(f"Edição aplicada ao Item 0x{item_id:X}: ATK={new_atk}, DEF={new_def}.")
    def _refresh_patch_tree(self):
        self.tree_patch.delete(*self.tree_patch.get_children())
        for offset, (old_b, new_b, item_id, field) in sorted(self.patcher.changes.items()):
            self.tree_patch.insert("", tk.END, values=(
                f"0x{offset:06X}",
                f"0x{item_id:X}",
                field,
                old_b.hex().upper(),
                new_b.hex().upper()
            ))
    def action_export_ips(self):
        if not self.patcher or not self.patcher.changes:
            messagebox.showwarning("Aviso", "Nenhuma alteração registrada para exportar.")
            return
        path = filedialog.asksaveasfilename(defaultextension=".ips", filetypes=[("Patch IPS", "*.ips")])
        if not path:
            return
        if self.patcher.generate_ips(path):
            messagebox.showinfo("Sucesso", f"Patch IPS gerado com sucesso em:\n{path}")
            self.log(f"Patch IPS salvo: {path}")
def main():
    root = tk.Tk()
    app = VH2EditorGUI(root)
    root.mainloop()
if __name__ == "__main__":
    main()