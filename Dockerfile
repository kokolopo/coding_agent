# Gunakan image Python 3.12 yang ramping
FROM python:3.12-slim

# Atur direktori kerja di dalam container
WORKDIR /app

# Salin file requirements.txt ke direktori kerja
COPY requirements.txt ./

# Instal semua dependensi dari requirements.txt
# Gunakan pip3 dan non-cache-dir untuk mengurangi ukuran image
RUN pip3 install --no-cache-dir -r requirements.txt

# Salin semua kode aplikasi Anda ke dalam container
COPY . .

ENV PYTHONPATH=/app/src

EXPOSE 7654

# Jalankan aplikasi saat container dimulai
# Pastikan nama file Python Anda adalah 'app.py' atau sesuaikan
CMD ["python3", "app.py"]