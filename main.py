import signal
import time
import gradio as gr
import os
import subprocess
from threading import Thread
import queue # PERUBAHAN: Import queue untuk komunikasi antar thread

# --- State Global untuk Mengelola Subprocess ---
# PERUBAHAN: Variabel global untuk menyimpan proses yang sedang berjalan
active_subprocess = None


# Menggunakan import asli dari struktur proyek Anda
from src.coding_agent.main import EngineeringFlow
from src.coding_agent.shared_queue import (
    TaskInfo,
    shared_task_output_queue,
    add_to_queue,
)


# --- Fungsi Helper untuk Thread ---

# PERUBAHAN: Fungsi ini akan berjalan di thread terpisah untuk membaca output
def enqueue_output(pipe, q):
    """Membaca output dari pipe (stdout) baris per baris dan memasukkannya ke dalam queue."""
    try:
        for line in iter(pipe.readline, ''):
            q.put(line)
    finally:
        pipe.close()


# --- Fungsi untuk Interaksi dengan UI ---

def run_and_stream(module_name: str, requirements: str):
    # ... (fungsi ini tidak perlu diubah)
    print("🚀 Background process started")
    
    if module_name.strip() == "" or requirements.strip() == "":
        gr.Warning("Nama Produk/Modul dan Kebutuhan Bisnis wajib diisi!")
        yield [{"role" : "assistant", "content" : "### ⚠️ Kolom wajib diisi..."}]
        return

    clean_module_name = module_name.strip()
    module_path = os.path.join("output", clean_module_name)
    
    if os.path.isdir(module_path):
        gr.Warning(f"Nama modul '{clean_module_name}' sudah ada!")
        yield [{"role": "assistant", "content": f"### ❌ Gagal: Nama modul '{clean_module_name}' sudah ada. Silakan gunakan nama lain."}]
        return

    thread = Thread(target=EngineeringFlow(clean_module_name, requirements).kickoff)
    thread.start()

    print("🚀 Memonitor antrian...")
    messages = [{"role": "assistant", "content": "Memulai engineering crew... 🚀"}]
    yield messages
    
    while thread.is_alive() or not shared_task_output_queue.empty():
        if not shared_task_output_queue.empty():
            task = shared_task_output_queue.get()
            print(f"🧲 {task.name} - {task.output}")

            if messages[-1]['role'] != 'assistant':
                 messages.append({"role": "assistant", "content": ""})
            
            stream_content = f"**{task.name}**: {task.output}\n\n"
            for char in stream_content:
                time.sleep(0.005)
                messages[-1]["content"] += char
                yield messages
        else:
            time.sleep(0.2)
    
    thread.join()
    messages.append({"role":"assistant", "content" : "# ✅ Semua Selesai!"})
    yield(messages)


def update_project_explorer(root_dir: str = "output"):
    # ... (fungsi ini tidak perlu diubah)
    if not os.path.exists(root_dir) or not os.listdir(root_dir):
        tree_md = "Direktori 'output' kosong. Jalankan proses untuk membuat proyek baru."
        projects = []
    else:
        tree = []
        for root, dirs, files in os.walk(root_dir):
            level = root.replace(root_dir, '').count(os.sep)
            indent = ' ' * 4 * level
            tree.append(f"{indent}📂 {os.path.basename(root)}/")
            sub_indent = ' ' * 4 * (level + 1)
            for f in files:
                tree.append(f"{sub_indent}📄 {f}")
        tree_md = "```\n" + '\n'.join(tree) + "\n```"
        projects = [d for d in os.listdir(root_dir) if os.path.isdir(os.path.join(root_dir, d))]
    project_dropdown_update = gr.Dropdown(choices=projects, label="Pilih Proyek untuk Dijalankan")
    return tree_md, project_dropdown_update


# PERUBAHAN BESAR: Fungsi ini sekarang memulai proses background dan men-stream outputnya
def run_selected_project(project_name: str):
    """
    Menjalankan proyek di latar belakang menggunakan Popen dan men-stream outputnya.
    """
    global active_subprocess
    if not project_name:
        gr.Warning("Silakan pilih proyek terlebih dahulu!")
        return
    
    # Hentikan proses lama jika ada yang masih berjalan
    if active_subprocess:
        active_subprocess.terminate()
        active_subprocess = None

    project_path = os.path.join("output", project_name)
    main_file_path = os.path.join(project_path, "app.py")

    if not os.path.exists(main_file_path):
        gr.Error(f"File 'app.py' tidak ditemukan di dalam '{project_name}'!")
        yield f"❌ Error: Tidak dapat menemukan 'app.py' di '{project_path}'.", gr.Button(interactive=True), gr.Button(visible=False), gr.Button(visible=False)
        return

    # Nonaktifkan tombol Run, tampilkan tombol Stop
    yield "🚀 Memulai proses...", gr.Button(interactive=False), gr.Button(visible=True), gr.Button(visible=True)

    try:
        # Gunakan Popen untuk memulai proses di latar belakang
        process = subprocess.Popen(
            ["uv", "run", "app.py"], # Opsi -u penting untuk unbuffered output
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
            cwd=project_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, # Gabungkan stderr ke stdout
            text=True,
            encoding='utf-8'
        )
        active_subprocess = process

        # Buat antrian dan thread untuk membaca output
        q = queue.Queue()
        thread = Thread(target=enqueue_output, args=(process.stdout, q))
        thread.daemon = True
        thread.start()

        full_output = ""
        # Loop untuk memantau antrian dan status proses
        while True:
            # Cek apakah proses sudah selesai
            if process.poll() is not None and q.empty():
                break
            
            try:
                # Ambil output dari antrian (dengan timeout)
                line = q.get_nowait()
                full_output += line
                yield full_output, gr.Button(interactive=False), gr.Button(visible=True), gr.Button(visible=True)
            except queue.Empty:
                # Jika antrian kosong, tidur sejenak
                time.sleep(0.1)
        
        # Proses selesai, kembalikan UI ke keadaan semula
        gr.Info(f"Proses '{project_name}' telah selesai.")
        yield full_output, gr.Button(interactive=True), gr.Button(visible=False), gr.Button(visible=False)

    except Exception as e:
        gr.Error("Gagal memulai proses!")
        yield f"❌ Error: {str(e)}", gr.Button(interactive=True), gr.Button(visible=False), gr.Button(visible=False)
    finally:
        active_subprocess = None


def open_project_link():
    return '<script>window.open("https://google.com", "_blank");</script>'

# PERUBAHAN: Fungsi stop sekarang menghentikan proses yang disimpan di variabel global
def stop_run():
    """Menghentikan subprocess yang sedang berjalan."""
    global active_subprocess
    if active_subprocess:
        gr.Warning(f"Menghentikan proses (PID: {active_subprocess.pid})...")
        active_subprocess.send_signal(signal.CTRL_BREAK_EVENT) # Kirim sinyal terminasi
        try:
            # Tunggu sebentar untuk memastikan proses benar-benar berhenti
            active_subprocess.wait(timeout=5)
        except subprocess.TimeoutExpired:
            # Jika tidak berhenti, paksa berhenti
            active_subprocess.kill()
            gr.Error("Proses tidak merespon, terpaksa dihentikan.")
            
        active_subprocess = None
        gr.Info("Proses berhasil dihentikan.")
        return "Proses dihentikan oleh pengguna.", gr.Button(interactive=True), gr.Button(visible=False)
    
    return "Tidak ada proses yang berjalan.", gr.Button(interactive=True), gr.Button(visible=False)


# --- UI dengan Gradio Blocks ---
with gr.Blocks(theme=gr.themes.Soft()) as demo:
    gr.Markdown("# 🤖 AI Engineering Crew")
    with gr.Row():
        # --- Kolom Sidebar (sebelah kiri) ---
        with gr.Column(scale=1, min_width=400):
            gr.Markdown("## 🗂️ Project Explorer")
            
            with gr.Accordion("🚀 Jalankan Proyek", open=True):
                project_dropdown = gr.Dropdown(label="Pilih Proyek untuk Dijalankan")
                with gr.Row():
                    run_project_btn = gr.Button("▶️ Run Selected Project", variant="secondary", scale=3)
                    stop_run_btn = gr.Button("⏹️ Stop", variant="stop", visible=False, scale=1)
                    
                project_output = gr.Code(label="Hasil Eksekusi Proyek", )
                open_project_btn = gr.Button("Buka Project", visible=False)
                

            with gr.Accordion("📁 Direktori Output", open=True):
                file_tree = gr.Markdown("Memuat...")
            
            refresh_btn = gr.Button("🔄 Refresh Explorer")

        # --- Kolom Utama (sebelah kanan) ---
        with gr.Column(scale=3):
            module_name = gr.Textbox(
                label="Nama Produk/Modul", placeholder="Contoh: 'API Autentikasi Pengguna'"
            )
            requirements = gr.Textbox(
                label="Kebutuhan Bisnis",
                placeholder="Contoh: 'Saya ingin membangun sebuah REST API...'",
                lines=3,
            )
            run_button = gr.Button("🚀 Buat Produk", variant="primary")
            chat = gr.Chatbot(type="messages", label="Output dari Crew", height=600, avatar_images=("assets/agent.png", "assets/robot.png"))

    # --- Interaktivitas Komponen UI ---
    
    run_button.click(
        fn=run_and_stream, inputs=[module_name, requirements], outputs=chat
    ).then(
        fn=update_project_explorer, outputs=[file_tree, project_dropdown]
    )

    # PERUBAHAN: Event handler sekarang memanggil fungsi generator streaming
    run_project_btn.click(
        fn=run_selected_project, 
        inputs=[project_dropdown], 
        outputs=[project_output, run_project_btn, stop_run_btn, open_project_btn]
    )

    open_project_btn.click(
        fn=None,  # No Python function needed for opening the link
        js="() => { window.open(`http://127.0.0.1:7860`, '_blank'); }"
    )
    
    # PERUBAHAN: Tombol stop sekarang memanggil fungsi stop_run yang baru
    stop_run_btn.click(
        fn=stop_run,
        inputs=None,
        outputs=[project_output, run_project_btn, stop_run_btn]
    )

    refresh_btn.click(fn=update_project_explorer, outputs=[file_tree, project_dropdown])
    demo.load(fn=update_project_explorer, outputs=[file_tree, project_dropdown])

demo.launch()