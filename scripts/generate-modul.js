const fs = require('fs');
const path = require('path');

// Setup Paths
const pdfDir = path.join(__dirname, '../data/pdf');
const modulDir = path.join(__dirname, '../modul');
const modulIndexPath = path.join(__dirname, '../modul.html');

// Buat folder modul jika belum ada
if (!fs.existsSync(modulDir)) {
    fs.mkdirSync(modulDir, { recursive: true });
}

function slugify(text) {
    return text.toString().toLowerCase().trim().replace(/\s+/g, '-').replace(/[^\w\-]+/g, '');
}

// 1. Baca semua file hasil konversi
// Pastikan folder data/pdf ada, jika tidak, script tidak akan error tapi buat folder kosong
if (!fs.existsSync(pdfDir)) {
    fs.mkdirSync(pdfDir, { recursive: true });
    console.log("Folder data/pdf belum ada, jadi dibuatkan otomatis.");
}

const files = fs.readdirSync(pdfDir).filter(file => file.endsWith('.pdf'));

let modulCards = '';

files.forEach(file => {
    // Hilangkan ekstensi .pdf untuk dapat judul asli
    const title = file.replace('.pdf', ''); 
    const slug = slugify(title);
    const modulUrl = `modul/${slug}.html`;

    // A. Buat Card untuk halaman modul.html (Index / Katalog)
    // Desain disesuaikan agar rapi dan mirip dengan Horizon Scan AI
    modulCards += `
        <a href="${modulUrl}" class="group bg-white p-6 rounded-2xl shadow-sm border border-slate-200 hover:shadow-md hover:border-brand-accent transition-all duration-300 flex flex-col justify-between h-full transform hover:-translate-y-1">
            <div>
                <div class="w-12 h-12 bg-[#00e6b8]/10 rounded-xl flex items-center justify-center mb-4 group-hover:scale-110 transition-transform">
                    <i class="ph-fill ph-presentation-chart text-2xl text-[#00e6b8]"></i>
                </div>
                <h3 class="font-bold text-xl text-slate-800 mb-2 leading-snug group-hover:text-brand-900">${title}</h3>
                <p class="text-sm text-slate-500 mb-4">Modul pelatihan interaktif berbasis presentasi.</p>
            </div>
            <span class="text-[#00e6b8] text-sm font-bold flex items-center gap-1 group-hover:text-[#00c29a] transition-colors mt-auto">
                Buka Modul <i class="ph-bold ph-arrow-right"></i>
            </span>
        </a>
    `;

    // B. Template untuk Halaman Modul Individu
    const singleModulHtml = `
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>${title} | Modul Pelatihan ICH Radar</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://unpkg.com/@phosphor-icons/web"></script>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
    <script>
        tailwind.config = {
            theme: {
                extend: {
                    fontFamily: { sans: ['Inter', 'sans-serif'] },
                    colors: {
                        brand: { 900: '#0f172a', accent: '#00e6b8' }
                    }
                }
            }
        }
    </script>
</head>
<body class="bg-slate-50 text-slate-800 font-sans antialiased h-screen flex flex-col overflow-hidden">
    
    <!-- Header Navigasi Simple -->
    <nav class="bg-white border-b border-slate-200 px-6 py-4 flex items-center justify-between shadow-sm z-10 shrink-0">
        <div class="flex items-center gap-4">
            <a href="../modul.html" class="flex items-center justify-center w-10 h-10 rounded-full bg-slate-100 hover:bg-slate-200 text-slate-600 transition-colors" title="Kembali ke Daftar">
                <i class="ph-bold ph-arrow-left text-lg"></i>
            </a>
            <h1 class="text-xl font-bold text-brand-900 truncate max-w-xl">${title}</h1>
        </div>
        <div class="hidden sm:flex items-center gap-2 text-sm font-medium text-slate-500 bg-slate-100 px-3 py-1.5 rounded-lg">
            <i class="ph-fill ph-file-pdf text-red-500"></i> Document Viewer
        </div>
    </nav>

    <!-- Area PDF Embed -->
    <main class="flex-1 w-full bg-slate-200/50 p-2 sm:p-6 overflow-hidden">
        <div class="w-full h-full bg-white rounded-xl shadow-lg border border-slate-200 overflow-hidden">
            <embed src="../data/pdf/${file}#toolbar=0&navpanes=0&scrollbar=0" type="application/pdf" width="100%" height="100%" class="w-full h-full" />
        </div>
    </main>

</body>
</html>
    `;

    // C. Simpan ke modul/modul-judul.html
    const outPath = path.join(modulDir, `${slug}.html`);
    fs.writeFileSync(outPath, singleModulHtml);
    console.log(`📄 Created Module: ${slug}.html`);
});

// Jika tidak ada modul, tampilkan teks kosong
if (files.length === 0) {
    modulCards = `
        <div class="col-span-full text-center py-12">
            <i class="ph-fill ph-folder-open text-6xl text-slate-300 mb-4"></i>
            <p class="text-slate-500 text-lg">Belum ada modul pelatihan yang tersedia.</p>
        </div>
    `;
}

// 2. Generate modul.html (Index / Katalog Modul)
const modulIndexHtml = `
<!DOCTYPE html>
<html lang="en" class="scroll-smooth">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Modul Pelatihan | ICH Radar</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://unpkg.com/@phosphor-icons/web"></script>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&display=swap" rel="stylesheet">
    <script>
        tailwind.config = {
            theme: {
                extend: {
                    fontFamily: { sans: ['Inter', 'sans-serif'] },
                    colors: {
                        brand: { 900: '#0f172a', accent: '#00e6b8' }
                    }
                }
            }
        }
    </script>
</head>
<body class="bg-slate-50 text-slate-800 font-sans antialiased">

    <!-- Navbar -->
    <nav class="bg-brand-900 border-b border-slate-700 sticky top-0 z-50">
        <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
            <div class="flex justify-between items-center h-16">
                <a href="index.html" class="flex items-center gap-2">
                    <i class="ph-fill ph-globe-hemisphere-east text-brand-accent text-3xl"></i>
                    <span class="font-bold text-xl text-white tracking-tight">ICH <span class="text-brand-accent">Radar</span></span>
                </a>
                <a href="index.html" class="text-sm font-bold text-slate-300 hover:text-brand-accent flex items-center gap-1 transition-colors">
                    <i class="ph-bold ph-house"></i> Back to Home
                </a>
            </div>
        </div>
    </nav>

    <!-- Hero Section -->
    <section class="pt-16 pb-12 bg-white text-center px-4 border-b border-slate-200">
        <div class="inline-flex items-center justify-center w-16 h-16 rounded-full bg-[#00e6b8]/10 text-[#00e6b8] mb-6">
            <i class="ph-fill ph-graduation-cap text-3xl"></i>
        </div>
        <h1 class="text-4xl md:text-5xl font-extrabold text-brand-900 mb-4 tracking-tight">Modul Pelatihan</h1>
        <p class="text-slate-500 max-w-2xl mx-auto text-lg">Pusat pembelajaran dan dokumentasi untuk pengembangan kapasitas (Capacity Building).</p>
    </section>

    <!-- Grid Katalog Modul -->
    <main class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-16">
        <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
            ${modulCards}
        </div>
    </main>

</body>
</html>
`;

fs.writeFileSync(modulIndexPath, modulIndexHtml);
console.log('\n✅ SUKSES!');
console.log(`📊 modul.html berhasil di-generate dengan ${files.length} modul.`);
