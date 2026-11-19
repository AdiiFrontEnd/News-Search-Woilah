# NEWS SEARCH V1.6
Pencarian berita lewat Google News RSS: pencarian biasa atau operator ala Google dorking
(`"frasa"`, `intitle:`, `site:`, `OR`, `-kata`, `when:`).

Baru di V1.1:
- **Tab pencarian** (maksimal 8). Tiap tab punya kueri, periode, dan pengaturan sendiri. Tab diingat saat browser dibuka lagi.
- **Refresh otomatis per tab** (5, 10, 15, 30, 60 menit). Berita baru diberi label BARU, badge angka di tab, dan notifikasi.
  Refresh berjalan selama halaman terbuka di browser.
- **Kueri Tersimpan**: simpan pencarian/dorking dengan nama, lalu salin, pakai di tab ini, atau buka di tab baru.
- Tombol **Salin kueri** di kotak pencarian.

Jalankan: klik dua kali `run_windows.bat`, lalu buka http://127.0.0.1:8001
Data lama dari NEWS SEARCH V1.0 bisa dipakai: salin folder `data` ke folder ini.

Desain V1.2: tampilan 3D, elegan, dan modern. Latar bola partikel 3D yang berputar mengikuti gerak mouse, kubus 3D berputar di judul,
kartu berita miring mengikuti kursor dengan efek kilau, panel kaca (glassmorphism), animasi masuk bertahap, dan mode gelap/terang otomatis
mengikuti pengaturan Windows. Animasi otomatis dimatikan jika Windows diatur "kurangi animasi". Semua fitur V1.1 tetap sama.

V1.3: tombol "Hapus semua" untuk Berita Tersimpan, Kueri Tersimpan, dan Riwayat (dengan konfirmasi). Tampilan lebih besar dan jelas
(huruf, tombol, kartu, dan jarak diperbesar, kontras teks naik). Tampilan lebih hidup: tepi panel bercahaya berputar, kilau pada tombol utama,
efek riak saat klik, sorotan cahaya mengikuti kursor, indikator hijau berkedip untuk tab dengan refresh otomatis, dan kerangka animasi saat memuat.

V1.4:
- Tombol "Tempel" di kotak pencarian dan di formulir Kueri Tersimpan (Ctrl+V tetap bisa dipakai). Teks multi-baris digabung jadi satu baris, maksimal 300 karakter.
- Tombol "Tampilan": tema cepat, pemilih warna latar, aksen utama, dan aksen kedua. Warna teks dan panel menyesuaikan otomatis agar tetap terbaca.
- Ukuran tulisan (80-150%) dan ukuran tampilan (80-130%). Ukuran default adalah 100% (ukuran V1.3). Tombol "Kembalikan ke default" mengembalikan semuanya.
- Pengaturan tampilan tersimpan di browser.
- Tab maksimal 20. Refresh otomatis antar-tab diberi jeda 1,5 detik agar permintaan tidak menumpuk.

V1.5:
- Edit untuk Kueri Tersimpan (judul, teks, periode), Berita Tersimpan (judul, kategori, wilayah), dan Riwayat (teks). Riwayat juga bisa dihapus satuan.
- Kategori: Regional (Maluku / Maluku Utara / gabungan), Nasional, Internasional (Geopolitik sebagai template utama), dan Sentimen negatif TNI.
  Pilih kategori lalu template dorking; hasil yang tersimpan diberi label kategori dan wilayah, dan bisa disaring di Berita Tersimpan.
- Penanda "Negatif TNI" otomatis muncul bila judul memuat kata TNI/prajurit dan kata negatif (pelanggaran, kasus, kekerasan, dll). Ini heuristik dari judul, bukan verifikasi fakta.
- Template umum (dorking) berisi pola yang tinggal diisi: intitle:, site:, frasa tepat, OR, dan kecualikan kata.
- Urutan default: terbaru.
- "Simpan teks pencarian": menyimpan teks pencarian dengan judul otomatis sama dengan teksnya (tanpa popup, tanpa duplikat).
- Tampilan: 15 tema, palet latar dan aksen, serta pemilih warna teks dan warna kartu.

V1.6:
- Berita TIDAK lagi tersimpan otomatis. Centang (atau Shift+klik untuk blok) berita yang diinginkan, lalu pilih: Arsipkan, + Daftar, Sematkan, atau Word.
- "Berita Tersimpan" diganti nama menjadi "Arsip Berita". Berita lama yang sudah tersimpan oleh versi sebelumnya tetap ada di arsip.
- Daftar Simpan: kumpulan berita pilihan dengan nama sendiri (misalnya untuk satu laporan). Bisa dibuka, diganti nama, disematkan, dihapus, dan diekspor ke Word.
- Sematkan: berita di arsip, kueri tersimpan, dan daftar simpan yang disematkan selalu tampil paling atas.
- Ekspor Word (.docx): tabel rapi berisi nomor, judul (dengan nama sumber), link yang bisa diklik, serta tanggal dan jam terbit (zona waktu komputer).
- Ekspor CSV/Excel dihapus.
- Warna: 12 tema "Cerah & kental" (latar benar-benar berwarna) dan slider "Kekuatan cahaya latar".
