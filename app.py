"""AudioSync Batch v3 - batch diagnostics and conservative sync suggestions."""
import json
import csv
import re
import statistics
import os
import queue
import shutil
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

EXTS = {'.mp4', '.mkv', '.mov', '.avi', '.m4v', '.webm', '.ts'}


def binary(name):
    base = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))
    extension = '.exe' if sys.platform == 'win32' else ''
    paths = [base / (name + extension), Path(sys.executable).parent / (name + extension)]
    for path in paths:
        if path.is_file():
            return str(path)
    return shutil.which(name)


def probe(path):
    if not binary('ffprobe'):
        raise RuntimeError('ffprobe absent : installez FFmpeg/FFprobe ou placez-les près de l’EXE.')
    cmd = [binary('ffprobe'), '-v', 'error', '-show_entries',
           'format=duration,start_time:stream=index,codec_type,codec_name,start_time,duration:stream_tags=language,title',
           '-of', 'json', str(path)]
    result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace',
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), timeout=30)
    if result.returncode:
        raise RuntimeError(result.stderr.strip()[-300:])
    return json.loads(result.stdout)


def stream_label(s):
    return {'video': 'Vidéo', 'audio': 'Audio', 'subtitle': 'Sous-titres', 'attachment': 'Pièce jointe', 'data': 'Données'}.get(s.get('codec_type'), 'Autre')


def format_time(v):
    if v is None or v == 'N/A':
        return '—'
    try:
        return f'{float(v):.3f} s'
    except (ValueError, TypeError):
        return '—'


def make_command(src, dest, offset_ms, selected, start=None, length=None):
    """Input 0: original video/subtitles; input 1: same file with audio timestamp offset."""
    ffmpeg = binary('ffmpeg')
    if not ffmpeg:
        raise RuntimeError('FFmpeg introuvable.')
    cmd = [ffmpeg, '-hide_banner', '-nostdin', '-loglevel', 'error', '-y']
    # Both inputs seek to the same time for small previews.
    if start is not None:
        cmd += ['-ss', str(start)]
    cmd += ['-i', str(src), '-itsoffset', f'{offset_ms / 1000:.3f}']
    if start is not None:
        cmd += ['-ss', str(start)]
    cmd += ['-i', str(src)]
    if length is not None:
        cmd += ['-t', str(length)]
    # Map each original stream index to the corresponding stream of the shifted input for audio.
    for s in selected:
        idx = int(s['index'])
        which = 1 if s['codec_type'] == 'audio' else 0
        cmd += ['-map', f'{which}:{idx}']
    cmd += ['-map_metadata', '0', '-map_chapters', '0', '-c', 'copy', '-max_interleave_delta', '0', str(dest)]
    return cmd



def diagnostic_analysis(path, info):
    """Report objective metadata anomalies; never equate metadata offset to lip synchronization."""
    streams = info.get('streams', [])
    videos = [s for s in streams if s.get('codec_type') == 'video']
    audios = [s for s in streams if s.get('codec_type') == 'audio']
    result = {'name': Path(path).name, 'path': path, 'status': 'À vérifier',
              'confidence': 'Non mesurable', 'suggestion_ms': '', 'difference_s': '',
              'audio_start_s': '', 'video_start_s': '', 'video_duration_s': '',
              'audio_duration_s': '', 'silence_start_s': '', 'notes': []}
    if not videos or not audios:
        result['notes'].append('Piste vidéo ou audio absente.')
        return result
    v, a = videos[0], audios[0]
    def number(value):
        try:
            return float(value)
        except (ValueError, TypeError):
            return None
    vs, aus = number(v.get('start_time')), number(a.get('start_time'))
    vd, ad = number(v.get('duration')), number(a.get('duration'))
    result['video_start_s'] = '' if vs is None else vs
    result['audio_start_s'] = '' if aus is None else aus
    result['video_duration_s'] = '' if vd is None else vd
    result['audio_duration_s'] = '' if ad is None else ad
    if vs is not None and aus is not None:
        d = aus - vs
        result['difference_s'] = round(d, 3)
        if abs(d) >= 0.25:
            result['status'] = 'Décalage des horodatages'
            result['notes'].append(f'Horodatages : audio - vidéo = {d:+.3f} s.')
            result['notes'].append('Ce décalage peut être normal : ne pas appliquer automatiquement sans contrôle visuel.')
        else:
            result['notes'].append('Horodatages de départ proches : synchronisation des paroles non vérifiée.')
    else:
        result['notes'].append('Horodatages de début incomplets.')
    if vd is not None and ad is not None and abs(vd-ad) >= 3:
        result['notes'].append(f'Durées de pistes différentes de {abs(vd-ad):.1f} s (génériques, silence ou montage possibles).')
        if result['status'] == 'À vérifier':
            result['status'] = 'Durées différentes'
    if len(audios) > 1:
        result['notes'].append(f'{len(audios)} pistes audio : contrôler la piste française souhaitée.')
    # First 60 seconds silence check: only indicates silence, never lip-sync evidence.
    ffmpeg = binary('ffmpeg')
    if ffmpeg:
        try:
            cmd = [ffmpeg, '-hide_banner', '-nostdin', '-i', str(path), '-map', '0:a:0',
                   '-t', '60', '-vn', '-af', 'silencedetect=noise=-38dB:d=0.6', '-f', 'null', '-']
            proc = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace',
                                  timeout=100, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            entries = re.findall(r'silence_start:\s*([0-9.]+)', proc.stderr)
            endings = re.findall(r'silence_end:\s*([0-9.]+)', proc.stderr)
            if entries and endings and float(entries[0]) <= 0.3:
                initial_silence = float(endings[0])
                result['silence_start_s'] = round(initial_silence, 3)
                if initial_silence >= 1:
                    result['notes'].append(f'Silence audio initial probable : {initial_silence:.1f} s.')
            if proc.returncode != 0:
                result['notes'].append('Détection du silence indisponible pour cette piste.')
        except (subprocess.TimeoutExpired, OSError, ValueError):
            result['notes'].append('Détection du silence non terminée.')
    result['notes'].append('Analyse labiale non réalisée : aucune valeur de correction certaine ne peut être déduite des métadonnées.')
    return result


class App:
    def __init__(self, root):
        self.root = root
        root.title('AudioSync Batch • V3 - Diagnostic')
        root.geometry('1120x820')
        root.minsize(780, 610)
        self.files = []
        self.infos = {}
        self.reports = {}
        self.enabled = {}
        self.events = queue.Queue()
        self.stop = threading.Event()
        self.busy = False
        self.proc = None
        self.offset = tk.StringVar(value='20000')
        self.direction = tk.StringVar(value='delay')
        self.dest = tk.StringVar(value=str(Path.home() / 'Videos' / 'AudioSync_Corrigees'))
        self.recursive = tk.BooleanVar(value=True)
        self.status = tk.StringVar(value='Ajoutez des vidéos pour consulter leurs pistes.')
        self.diagnostic = tk.StringVar(value='Sélectionnez un fichier ou lancez Analyser tout le dossier.')
        self.preview_start = tk.StringVar(value='30')
        self.build_ui()
        root.after(100, self.poll)

    def build_ui(self):
        bg, panel, fg, aqua = '#101725', '#1c283b', '#eef3fb', '#3edbd0'
        self.root.configure(bg=bg)
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('TFrame', background=bg)
        style.configure('TLabel', background=bg, foreground=fg, font=('Segoe UI', 10))
        style.configure('Title.TLabel', background=bg, foreground=aqua, font=('Segoe UI', 20, 'bold'))
        style.configure('TButton', padding=7)
        style.configure('TCheckbutton', background=bg, foreground=fg)
        style.configure('TRadiobutton', background=bg, foreground=fg)
        style.configure('Treeview', background=panel, fieldbackground=panel, foreground=fg, rowheight=25,
                        borderwidth=0, font=('Segoe UI', 10))
        style.map('Treeview', background=[('selected', '#136e78')], foreground=[('selected', '#ffffff')])
        style.configure('Treeview.Heading', font=('Segoe UI', 10, 'bold'))
        main = ttk.Frame(self.root, padding=14)
        main.pack(fill='both', expand=True)
        ttk.Label(main, text='◉ AudioSync Batch', style='Title.TLabel').pack(anchor='w')
        ttk.Label(main, text='Analyse des pistes • Décalage en lot • Copie sans réencodage • Originaux préservés').pack(anchor='w', pady=(0, 8))
        bar = ttk.Frame(main)
        bar.pack(fill='x')
        ttk.Button(bar, text='Ajouter des vidéos', command=self.add_files).pack(side='left', padx=(0, 6))
        ttk.Button(bar, text='Ajouter un dossier', command=self.add_folder).pack(side='left', padx=(0, 6))
        ttk.Button(bar, text='Vider', command=self.clear).pack(side='left')
        self.scan_btn = ttk.Button(bar, text='Analyser toutes les vidéos', command=self.scan_all)
        self.scan_btn.pack(side='left', padx=8)
        ttk.Button(bar, text='Exporter le rapport CSV', command=self.export_report).pack(side='left')
        ttk.Checkbutton(bar, text='Sous-dossiers', variable=self.recursive).pack(side='right')
        ttk.Label(main, text='Fichiers source').pack(anchor='w', pady=(12, 3))
        file_frame = ttk.Frame(main)
        file_frame.pack(fill='both', expand=True)
        self.files_view = ttk.Treeview(file_frame, columns=('container', 'count', 'analysis'), show='tree headings', height=7)
        self.files_view.heading('#0', text='Nom du fichier')
        self.files_view.heading('container', text='Conteneur')
        self.files_view.heading('count', text='Pistes')
        self.files_view.heading('analysis', text='Diagnostic')
        self.files_view.column('#0', width=520)
        self.files_view.column('container', width=130)
        self.files_view.column('count', width=90, anchor='center')
        self.files_view.column('analysis', width=215)
        self.files_view.pack(side='left', fill='both', expand=True)
        sb = ttk.Scrollbar(file_frame, command=self.files_view.yview)
        sb.pack(side='right', fill='y')
        self.files_view.configure(yscrollcommand=sb.set)
        self.files_view.bind('<<TreeviewSelect>>', self.on_select_file)
        ttk.Label(main, text='Pistes du fichier sélectionné (double-clic pour inclure/exclure)').pack(anchor='w', pady=(10, 3))
        tracks_frame = ttk.Frame(main)
        tracks_frame.pack(fill='both', expand=True)
        self.tracks = ttk.Treeview(tracks_frame, columns=('use', 'codec', 'kind', 'lang', 'start', 'title'), show='headings', height=7)
        for col, label, width in [('use', 'Copier', 65), ('codec', 'Codec', 115), ('kind', 'Type', 105),
                                  ('lang', 'Langue', 65), ('start', 'Début', 85), ('title', 'Nom', 200)]:
            self.tracks.heading(col, text=label)
            self.tracks.column(col, width=width, anchor='center' if col in ('use', 'lang', 'start') else 'w')
        self.tracks.pack(side='left', fill='both', expand=True)
        sb2 = ttk.Scrollbar(tracks_frame, command=self.tracks.yview)
        sb2.pack(side='right', fill='y')
        self.tracks.configure(yscrollcommand=sb2.set)
        self.tracks.bind('<Double-1>', self.toggle_track)
        ttk.Label(main, textvariable=self.diagnostic, wraplength=980).pack(anchor='w', pady=(8, 6))
        config = ttk.Frame(main)
        config.pack(fill='x', pady=5)
        ttk.Label(config, text='Décalage :').pack(side='left')
        ttk.Entry(config, textvariable=self.offset, width=10).pack(side='left', padx=(8, 4))
        ttk.Label(config, text='ms').pack(side='left', padx=(0, 14))
        ttk.Radiobutton(config, text='Retarder le son', variable=self.direction, value='delay').pack(side='left', padx=5)
        ttk.Radiobutton(config, text='Avancer le son', variable=self.direction, value='advance').pack(side='left', padx=5)
        ttk.Label(config, text='Test à partir de :').pack(side='left', padx=(18, 4))
        ttk.Entry(config, textvariable=self.preview_start, width=6).pack(side='left')
        ttk.Label(config, text='secondes').pack(side='left', padx=4)
        output = ttk.Frame(main)
        output.pack(fill='x', pady=5)
        ttk.Label(output, text='Dossier de sortie :').pack(side='left')
        ttk.Entry(output, textvariable=self.dest).pack(side='left', fill='x', expand=True, padx=8)
        ttk.Button(output, text='Parcourir', command=self.choose_output).pack(side='left')
        actions = ttk.Frame(main)
        actions.pack(fill='x', pady=8)
        self.test_btn = ttk.Button(actions, text='Créer un extrait test (15 s)', command=self.test)
        self.test_btn.pack(side='left', padx=(0, 8))
        self.run_btn = ttk.Button(actions, text='Corriger toutes les vidéos', command=self.start)
        self.run_btn.pack(side='left', padx=(0, 8))
        self.cancel_btn = ttk.Button(actions, text='Arrêter', command=self.cancel, state='disabled')
        self.cancel_btn.pack(side='left')
        self.progress = ttk.Progressbar(main, mode='determinate')
        self.progress.pack(fill='x', pady=(4, 4))
        ttk.Label(main, textvariable=self.status, wraplength=970).pack(anchor='w')
        ttk.Label(main, text='Analyse automatique des anomalies techniques ; aucun décalage de paroles n’est inventé. Pour une correction, vérifier un extrait avant le lot.',
                  wraplength=970).pack(anchor='w', pady=(5, 0))

    def add(self, paths):
        known = set(self.files)
        for raw in paths:
            p = Path(raw).resolve()
            if not p.is_file() or p.suffix.lower() not in EXTS or p in known:
                continue
            known.add(p)
            self.files.append(p)
            self.files_view.insert('', 'end', iid=str(p), text=p.name, values=(p.suffix.upper().lstrip('.'), 'À analyser', 'Non analysé'))
        self.status.set(f'{len(self.files)} vidéo(s) chargée(s).')
        if self.files and not self.files_view.selection():
            self.files_view.selection_set(str(self.files[0]))

    def add_files(self):
        self.add(filedialog.askopenfilenames(filetypes=[('Vidéos', '*.mp4 *.mkv *.mov *.avi *.m4v *.webm *.ts')]))

    def add_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            root = Path(folder)
            self.add(sorted(root.rglob('*') if self.recursive.get() else root.glob('*')))

    def clear(self):
        if self.busy:
            return
        self.files.clear()
        self.infos.clear()
        self.reports.clear()
        self.enabled.clear()
        self.files_view.delete(*self.files_view.get_children())
        self.tracks.delete(*self.tracks.get_children())
        self.diagnostic.set('Sélectionnez un fichier pour analyser ses horodatages.')
        self.status.set('Liste vidée.')

    def choose_output(self):
        folder = filedialog.askdirectory()
        if folder:
            self.dest.set(folder)

    def selected_file(self):
        selection = self.files_view.selection()
        return Path(selection[0]) if selection else None

    def on_select_file(self, _event=None):
        p = self.selected_file()
        if not p:
            return
        self.tracks.delete(*self.tracks.get_children())
        if str(p) in self.infos:
            self.populate_tracks(str(p))
        else:
            self.diagnostic.set('Analyse du fichier en cours…')
            threading.Thread(target=self.inspect, args=(str(p),), daemon=True).start()

    def inspect(self, path):
        try:
            self.events.put(('probe', (path, probe(path), None)))
        except Exception as exc:
            self.events.put(('probe', (path, None, str(exc))))

    def populate_tracks(self, path):
        data = self.infos[path]
        self.tracks.delete(*self.tracks.get_children())
        enabled = self.enabled.setdefault(path, {s['index'] for s in data.get('streams', []) if s.get('codec_type') in ('video', 'audio', 'subtitle', 'attachment')})
        streams = data.get('streams', [])
        for s in streams:
            if s.get('codec_type') not in ('video', 'audio', 'subtitle', 'attachment'):
                continue
            idx = s['index']
            tags = s.get('tags', {})
            self.tracks.insert('', 'end', iid=f'stream-{idx}', values=(
                '✓ Oui' if idx in enabled else 'Non', s.get('codec_name', '?'), stream_label(s),
                tags.get('language', 'und'), format_time(s.get('start_time')), tags.get('title', '')))
        v = next((s for s in streams if s.get('codec_type') == 'video'), None)
        a = next((s for s in streams if s.get('codec_type') == 'audio'), None)
        if v and a:
            try:
                delta = float(a.get('start_time', 0)) - float(v.get('start_time', 0))
                interpretation = 'Le son démarre avant la vidéo.' if delta < -0.05 else ('Le son démarre après la vidéo.' if delta > 0.05 else 'Les débuts sont proches ; un décalage réel peut venir du contenu.')
                desc = f'Diagnostic : début audio - début vidéo = {delta:+.3f} s. {interpretation}'
            except (TypeError, ValueError):
                desc = 'Diagnostic : horodatages de début indisponibles.'
        else:
            desc = 'Diagnostic : piste audio ou vidéo absente.'
        self.diagnostic.set((' | '.join(self.reports[path]['notes']) if path in self.reports else desc + ' Ces horodatages ne prouvent pas à eux seuls la synchronisation des paroles.'))
        self.files_view.set(path, 'count', str(len(streams)))

    def scan_all(self):
        if self.busy or not self.files:
            if not self.files:
                messagebox.showinfo('Aucune vidéo', 'Ajoutez des fichiers ou un dossier.')
            return
        if not binary('ffprobe'):
            messagebox.showerror('FFprobe absent', 'ffprobe.exe est nécessaire pour analyser les pistes.')
            return
        self.busy = True
        self.stop.clear()
        self.scan_btn.configure(state='disabled')
        self.progress.configure(maximum=len(self.files), value=0)
        self.cancel_btn.configure(state='normal')
        threading.Thread(target=self.scan_worker, daemon=True).start()

    def scan_worker(self):
        for index, p in enumerate(self.files, 1):
            if self.stop.is_set():
                break
            self.events.put(('status', f'Analyse {index}/{len(self.files)} : {p.name}'))
            try:
                info = self.infos.get(str(p)) or probe(p)
                report = diagnostic_analysis(str(p), info)
                self.events.put(('scan_result', (str(p), info, report)))
            except Exception as exc:
                self.events.put(('scan_error', (str(p), str(exc))))
            self.events.put(('progress', index))
        self.events.put(('scan_done', 'Analyse terminée. Les anomalies détectées sont des indices, pas une preuve de synchronisation.'))

    def export_report(self):
        if not self.reports:
            messagebox.showinfo('Rapport vide', 'Lancez « Analyser toutes les vidéos » avant export.')
            return
        path = filedialog.asksaveasfilename(defaultextension='.csv', filetypes=[('CSV', '*.csv')], initialfile='audiosync_diagnostic_v3.csv')
        if not path:
            return
        fields = ['name', 'path', 'status', 'confidence', 'suggestion_ms', 'difference_s',
                  'audio_start_s', 'video_start_s', 'audio_duration_s', 'video_duration_s', 'silence_start_s', 'notes']
        with open(path, 'w', newline='', encoding='utf-8-sig') as out:
            writer = csv.DictWriter(out, fieldnames=fields, delimiter=';')
            writer.writeheader()
            for report in self.reports.values():
                writer.writerow({k: ' | '.join(report[k]) if k == 'notes' else report.get(k, '') for k in fields})
        self.status.set(f'Rapport exporté : {path}')

    def toggle_track(self, event):
        path = self.selected_file()
        if not path or str(path) not in self.infos:
            return
        row = self.tracks.identify_row(event.y)
        if not row:
            return
        idx = int(row.split('-')[1])
        en = self.enabled[str(path)]
        if idx in en:
            en.remove(idx)
        else:
            en.add(idx)
        self.populate_tracks(str(path))

    def settings(self):
        if self.busy:
            return None
        if not self.files:
            messagebox.showwarning('Liste vide', 'Ajoutez au moins une vidéo.')
            return None
        if not binary('ffmpeg') or not binary('ffprobe'):
            messagebox.showerror('FFmpeg absent', 'Installez FFmpeg avec ffprobe et ajoutez-les au PATH, ou placez les deux EXE à côté du programme.')
            return None
        try:
            ms = int(self.offset.get().strip())
            if ms < 0 or ms > 600000:
                raise ValueError
            sec = float(self.preview_start.get().strip())
            if sec < 0:
                raise ValueError
        except ValueError:
            messagebox.showerror('Valeur incorrecte', 'Décalage : entre 0 et 600000 ms. Début du test : nombre positif de secondes.')
            return None
        if not self.dest.get().strip():
            messagebox.showerror('Sortie manquante', 'Choisissez un dossier de sortie.')
            return None
        return (ms if self.direction.get() == 'delay' else -ms, sec)

    def test(self):
        settings = self.settings()
        if settings is None:
            return
        src = self.selected_file() or self.files[0]
        self.launch([src], settings[0], preview=True, start=settings[1])

    def start(self):
        settings = self.settings()
        if settings is None:
            return
        offset = settings[0]
        if messagebox.askyesno('Confirmer', f'Corriger {len(self.files)} vidéos avec {offset:+d} ms ?\nOriginales préservées ; sortie MKV sans réencodage.'):
            self.launch(list(self.files), offset)

    def launch(self, files, offset, preview=False, start=0):
        self.busy = True
        self.stop.clear()
        self.progress.configure(maximum=len(files), value=0)
        self.run_btn.configure(state='disabled')
        self.test_btn.configure(state='disabled')
        self.cancel_btn.configure(state='normal')
        self.scan_btn.configure(state='disabled')
        threading.Thread(target=self.worker, args=(files, offset, preview, start), daemon=True).start()

    def cancel(self):
        self.stop.set()
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
        self.status.set('Arrêt demandé…')

    def worker(self, files, offset, preview, start):
        errors = []
        successful = 0
        try:
            outdir = Path(self.dest.get()).expanduser()
            outdir.mkdir(parents=True, exist_ok=True)
            for no, p in enumerate(files, 1):
                if self.stop.is_set():
                    break
                try:
                    data = self.infos.get(str(p)) or probe(p)
                    streams = [s for s in data.get('streams', []) if s['index'] in self.enabled.get(str(p), {x['index'] for x in data.get('streams', [])}) and s.get('codec_type') in ('video', 'audio', 'subtitle', 'attachment')]
                    if not any(s.get('codec_type') == 'audio' for s in streams):
                        raise ValueError('Aucune piste audio sélectionnée.')
                    if not any(s.get('codec_type') == 'video' for s in streams):
                        raise ValueError('Aucune piste vidéo sélectionnée.')
                    suffix = '_test_sync' if preview else '_synchronise'
                    dest = outdir / f'{p.stem}{suffix}.mkv'
                    k = 2
                    while dest.exists() or dest.resolve() == p.resolve():
                        dest = outdir / f'{p.stem}{suffix}_{k}.mkv'
                        k += 1
                    tmp = dest.with_name(dest.stem + '.part.mkv')
                    self.events.put(('status', f'{no}/{len(files)} : {p.name}'))
                    cmd = make_command(p, tmp, offset, streams, start if preview else None, 15 if preview else None)
                    self.proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
                                                 encoding='utf-8', errors='replace', creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                    _, err = self.proc.communicate()
                    if self.stop.is_set():
                        tmp.unlink(missing_ok=True)
                        break
                    if self.proc.returncode:
                        raise RuntimeError(err.strip()[-350:] or 'FFmpeg a échoué.')
                    tmp.replace(dest)
                    successful += 1
                except Exception as exc:
                    errors.append(f'{p.name} : {exc}')
                    try:
                        tmp.unlink(missing_ok=True)
                    except (OSError, UnboundLocalError):
                        pass
                finally:
                    self.proc = None
                self.events.put(('progress', no))
            state = 'Traitement interrompu. ' if self.stop.is_set() else ''
            result = f'{state}{successful}/{len(files)} fichier(s) enregistré(s) dans {outdir}'
            if errors:
                result += f' | {len(errors)} erreur(s) : ' + '; '.join(errors[:2])
            self.events.put(('done', result))
        except Exception as exc:
            self.events.put(('done', f'Erreur : {exc}'))

    def poll(self):
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == 'status':
                    self.status.set(value)
                elif kind == 'progress':
                    self.progress['value'] = value
                elif kind == 'scan_result':
                    path, info, report = value
                    self.infos[path] = info
                    self.reports[path] = report
                    if self.files_view.exists(path):
                        self.files_view.set(path, 'count', str(len(info.get('streams', []))))
                        self.files_view.set(path, 'analysis', report['status'])
                    if str(self.selected_file()) == path:
                        self.populate_tracks(path)
                elif kind == 'scan_error':
                    path, error = value
                    if self.files_view.exists(path):
                        self.files_view.set(path, 'analysis', 'Erreur')
                    self.status.set(f'{Path(path).name} : {error}')
                elif kind == 'scan_done':
                    self.busy = False
                    self.status.set(value)
                    self.scan_btn.configure(state='normal')
                    self.cancel_btn.configure(state='disabled')
                elif kind == 'probe':
                    path, info, error = value
                    if error:
                        self.status.set(f'Analyse impossible ({Path(path).name}) : {error}')
                    else:
                        self.infos[path] = info
                        if str(self.selected_file()) == path:
                            self.populate_tracks(path)
                elif kind == 'done':
                    self.busy = False
                    self.status.set(value)
                    self.run_btn.configure(state='normal')
                    self.test_btn.configure(state='normal')
                    self.cancel_btn.configure(state='disabled')
                    self.scan_btn.configure(state='normal')
        except queue.Empty:
            pass
        self.root.after(100, self.poll)


if __name__ == '__main__':
    root = tk.Tk()
    App(root)
    root.mainloop()
