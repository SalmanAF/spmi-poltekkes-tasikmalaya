# Sumber dokumen bersama

`documents.json` adalah sumber data tunggal untuk API admin dan seluruh halaman publik. Dokumen publik hanya jika `status` bernilai tepat `publik`; `draft` tidak pernah disajikan oleh API publik, preview, atau download.

Contoh record:

```json
{
  "id": "doc-169823001",
  "judul": "Standar Penjaminan Mutu Internal",
  "kode": "STD-01",
  "no_dokumen": "STD-01",
  "kategori": "Standar PT",
  "tipe_sumber": "local_file",
  "file_url": "/uploads/doc-169823001.pdf",
  "link_download": "/uploads/doc-169823001.pdf",
  "tahun": "2026",
  "status": "publik",
  "is_downloadable": true,
  "created_at": "2026-09-29T12:00:00+00:00"
}
```

Nilai kategori: `Kebijakan`, `Standar PT`, `Pedoman`, `SOP`, `Formulir`, `Perangkat SPMI`, `Unduhan`, `Lainnya`. Nilai sumber: `drive_link` atau `local_file`; status: `publik`, `privat`, atau `draft`. Record tanpa field `status` dibaca sebagai `publik`. Hanya status `publik` disajikan pada halaman User, sedangkan Admin dapat melihat semua status. Berkas lokal hanya PDF/DOCX, disimpan langsung di folder ini, dan tidak dipasang sebagai static directory. Maksimum unggahan 20 MB.

`kode` dan `link_download` merupakan nama field untuk formulir admin Pedoman/SOP; keduanya disinkronkan dengan `no_dokumen` dan `file_url` agar record lama tetap terbaca. `tahun` digunakan oleh katalog publik untuk filter dan label tahun. API admin kategori menyediakan `POST /admin/documents/add`, `POST /admin/documents/edit/{id}`, `POST /admin/documents/delete/{id}`, dan `POST /admin/documents/toggle-status/{id}`. API tersebut membutuhkan sesi admin yang valid dan perlindungan CSRF; integrasi lama dapat menggunakan token Bearer jika `SPMI_ADMIN_TOKEN` telah dikonfigurasi. Impor ulang Excel mempertahankan status berdasarkan ID dokumen agar pilihan Privat Admin tidak berubah menjadi Publik.

Relasi Peta Integrasi menggunakan ID dokumen: isi `standard_id` pada Pedoman dengan ID Standar PT, lalu isi `guideline_id` pada SOP dengan ID Pedoman. `parent_document_id` pada data impor SOP dibaca sebagai nama lama untuk relasi Pedoman tersebut. Di Admin > Pedoman dan Admin > SOP, pilih dokumen induk pada kolom relasi sebelum menyimpan. Untuk data SOP lama tanpa `guideline_id`, Peta Integrasi menampilkan SOP yang memiliki `standard_id` sama dengan Pedoman sebagai relasi cadangan; relasi langsung ke Pedoman selalu lebih spesifik.

Impor sheet `Integrasi Standar 2022` dan `Integrasi Standar 2025` memakai penanda kolom `No` untuk membedakan Standar induk dari judul turunannya. Baris bernomor menjadi Standar, baris judul berikutnya menjadi dokumen/subjudul sampai Standar berikutnya, dan SOP ditempelkan ke Pedoman terakhir di bawah Standar tersebut hanya bila urutan baris di sheet memang menunjukkan relasi itu. ID integrasi menyertakan tahun agar dokumen kedua sheet tidak saling menimpa. Label kelompok dari sheet disimpan pada `subjudul`; judul baris turunan disimpan persis pada `judul`. Peta Integrasi hanya memakai record bertanda `tahun_integrasi` 2022 atau 2025 agar dokumen dari sheet register Pedoman/SOP lain tidak tercampur atau tampak sebagai relasi yang tidak ada di sheet.

Halaman Admin > Perangkat SPMI menampilkan seluruh record dari sheet `Integrasi Standar 2025`, dikelompokkan menurut Standar induk atau sebagai dokumen umum bila tidak memiliki induk. Judul, nomor dokumen, PIC, status, dan tautan sumber ditampilkan dari manifest impor; halaman ini merupakan tampilan data sheet, sehingga perubahan isi workbook harus dimuat melalui skrip impor.

## Monitoring dan PPEPP

Identitas serta file dokumen tetap bersumber dari `documents.json`. Data monitoring dan tahapan PPEPP disimpan dalam tabel tambahan di SQLite `uploads/admin_auth.sqlite3`; tabel `implementation_documents` menyinkronkan ID, judul, dan kategori dokumen yang terdaftar sebagai target foreign key tanpa memindahkan atau mengubah manifest dokumen.

- `implementation_monitoring` menyimpan unit pelaksana, PIC, bukti, tanggal, dan catatan per ID dokumen.
- `ppepp_stages` menyimpan aktivitas utama, dokumen yang digunakan, output, frekuensi, dan narasi per ID dokumen serta tahap. Kombinasi `(document_id, stage)` unik sehingga simpan ulang memperbarui record yang ada.
- Record PPEPP memiliki foreign key ke ID dokumen dan tahapan dibatasi pada `penetapan`, `pelaksanaan`, `evaluasi`, `pengendalian`, dan `peningkatan`. Tabel ditambahkan dengan `CREATE TABLE IF NOT EXISTS`; data akun dan manifest lama tidak dihapus.
- Halaman Admin > Monitoring mengambil data terbaru dan membuka Admin > Implementasi menggunakan ID dokumen. Halaman tersebut menampilkan kelengkapan isian narasi secara terpisah dari status keterlaksanaan kegiatan.
- Endpoint admin untuk membaca, menyimpan, dan menghapus PPEPP berada di `/api/admin/implementations`; endpoint mutasi memerlukan sesi admin dan token CSRF.

## Akses Admin

Dashboard, halaman Pengaturan, dan endpoint CRUD dokumen dilindungi akun admin. Registrasi langsung membuat akun aktif yang dapat digunakan untuk login. Password disimpan dengan scrypt dalam database SQLite `uploads/admin_auth.sqlite3`.

Tetapkan secret sesi dan token setup awal melalui environment terminal sebelum menjalankan server. Buat nilai acak yang berbeda dan jangan simpan secret di kode atau repository:

```powershell
$env:SPMI_SESSION_SECRET = (& .\venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(48))")
$env:SPMI_ADMIN_SETUP_TOKEN = (& .\venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(48))")
uvicorn main:app --reload
```

Buka `/admin/setup` untuk membuat administrator pertama dengan token setup tersebut. Setup hanya dapat membuat administrator saat belum ada akun admin aktif. Setelah berhasil, hapus `SPMI_ADMIN_SETUP_TOKEN` dari environment. Akun selanjutnya dapat langsung dibuat melalui `/admin/register` dan langsung digunakan untuk login. Akun lama yang berstatus menunggu persetujuan akan otomatis diaktifkan saat database diinisialisasi. Jika secret sesi tidak diatur, server membuat secret acak sementara dan semua sesi berakhir saat proses server dimulai ulang. Untuk production gunakan HTTPS dan tetapkan `SPMI_COOKIE_SECURE=true`.

API dokumen menerima sesi admin dari browser dengan perlindungan CSRF. Integrasi lama juga dapat memakai `Authorization: Bearer <SPMI_ADMIN_TOKEN>` jika secret opsional `SPMI_ADMIN_TOKEN` disetel; endpoint admin tetap menolak permintaan tanpa autentikasi.

Untuk link Drive non-downloadable, viewer diarahkan ke `/preview`; kebijakan berbagi Google Drive tetap harus membatasi hak unduh pada sisi Google Drive.
