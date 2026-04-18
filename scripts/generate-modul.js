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
    // Desain Dark Mode OSINT Theme - Sesuai Landing Page
    modulCards += `
        <a href="${modulUrl}" class="text-left bg-[#0a0a0a] border border-brand-700 p-8 rounded-3xl hover:border-[#00ffcc] hover:shadow-[0_10px_30px_rgba(0,255,204,0.1)] transition-all group flex flex-col h-full relative overflow-hidden">
            <div class="absolute top-0 right-0 w-32 h-32 bg-brand-accent/5 rounded-bl-full pointer-events-none group-hover:bg-brand-accent/10 transition-colors"></div>
            
            <div class="w-14 h-14 bg-brand-800 rounded-2xl flex items-center justify-center text-brand-accent text-2xl mb-6 border border-brand-700 group-hover:scale-110 transition-transform shadow-lg relative z-10">
                <i class="ph-fill ph-presentation-chart"></i>
            </div>
            
            <h4 class="text-xl font-display font-bold text-white mb-3 relative z-10 group-hover:text-brand-accent transition-colors">${title}</h4>
            <p class="text-sm text-gray-400 flex-grow mb-6 relative z-10">Capacity Building Module / Interactive Presentation Data.</p>
            
            <span class="text-brand-accent text-xs font-bold uppercase tracking-wider flex items-center gap-1 relative z-10">
                Access Module <i class="ph-bold ph-arrow-right"></i>
            </span>
        </a>
    `;

    // B. Template untuk Halaman Modul Individu (PDF Viewer)
    const singleModulHtml = `
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>${title} | ICH Radar Modules</title>
    
    <!-- Google Fonts -->
    <link rel="preconnect" href="https://fonts.googleapis.com" />
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;600;700&family=Inter:wght@400;500;700&display=swap" rel="stylesheet" />
    
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://unpkg.com/@phosphor-icons/web"></script>
    
    <!-- Tailwind Configuration -->
    <script>
        tailwind.config = {
            theme: {
                extend: {
                    fontFamily: {
                        sans:['Inter', 'sans-serif'],
                        display:['Space Grotesk', 'sans-serif'],
                    },
                    colors: {
                        brand: {
                            900: '#0a0a0a',
                            800: '#141414',
                            700: '#1f1f1f',
                            accent: '#00ffcc',
                            secondary: '#facc15',
                            journal: '#ff00aa'
                        }
                    }
                }
            }
        }
    </script>
    
    <!-- Custom Styles (Grid Background) -->
    <style>
        body { background-color: #0a0a0a; color: #f5f5f5; overflow-x: hidden; }
        .bg-grid {
            background-size: 40px 40px;
            background-image: linear-gradient(to right, rgba(255, 255, 255, 0.05) 1px, transparent 1px),
                              linear-gradient(to bottom, rgba(255, 255, 255, 0.05) 1px, transparent 1px);
        }
    </style>
</head>
<body class="bg-brand-900 text-white font-sans antialiased h-screen flex flex-col overflow-hidden bg-grid">
    
    <!-- Header Navigasi -->
    <nav class="bg-brand-900/80 backdrop-blur-md border-b border-brand-700 px-6 py-4 flex items-center justify-between shadow-sm z-50 shrink-0">
        <div class="flex items-center gap-4">
            <a href="../modul.html" class="flex items-center justify-center w-10 h-10 rounded-xl bg-brand-800 border border-brand-700 hover:border-brand-accent text-gray-400 hover:text-brand-accent transition-colors" title="Back to Modules">
                <i class="ph-bold ph-arrow-left text-lg"></i>
            </a>
            <h1 class="text-xl font-display font-bold text-white truncate max-w-xl hidden sm:block">${title}</h1>
        </div>
        <div class="flex items-center gap-3">
            <div class="hidden sm:flex items-center gap-2 text-xs font-mono uppercase tracking-widest text-brand-accent bg-brand-800 border border-brand-700 px-3 py-1.5 rounded-lg">
                <span class="w-2 h-2 rounded-full bg-brand-accent animate-pulse"></span>
                Secure Document Viewer
            </div>
            <div class="w-10 h-10 rounded-xl bg-brand-800 border border-brand-700 flex items-center justify-center text-red-400">
                <i class="ph-fill ph-file-pdf text-xl"></i>
            </div>
        </div>
    </nav>

    <!-- Area PDF Embed -->
    <main class="flex-1 w-full p-2 sm:p-6 overflow-hidden relative">
        <!-- Ambient Glow -->
        <div class="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] bg-brand-accent/10 rounded-full blur-[120px] pointer-events-none z-0"></div>
        
        <div class="w-full h-full bg-[#111] rounded-2xl shadow-[0_0_50px_rgba(0,255,204,0.1)] border border-brand-700 overflow-hidden relative z-10">
            <!-- Parameter toolbar=0 menyembunyikan UI acrobat standar agar lebih clean -->
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

// Jika tidak ada modul, tampilkan UI "Empty State" ala OSINT
if (files.length === 0) {
    modulCards = `
        <div class="col-span-full text-center py-24 border border-brand-700 border-dashed rounded-3xl bg-brand-800/30 backdrop-blur-sm relative overflow-hidden">
            <div class="absolute inset-0 bg-brand-accent/5"></div>
            <i class="ph-fill ph-database text-6xl text-brand-700 mb-4 animate-pulse relative z-10"></i>
            <h3 class="font-display font-bold text-2xl text-white mb-2 relative z-10">No Documents Found</h3>
            <p class="text-gray-500 font-mono text-sm uppercase tracking-widest relative z-10">Database is currently empty. Upload PPTX to sync.</p>
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
    <title>Learning Hub | ICH Radar</title>
    
    <!-- Google Fonts -->
    <link rel="preconnect" href="https://fonts.googleapis.com" />
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;600;700&family=Inter:wght@400;500;700&display=swap" rel="stylesheet" />
    
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://unpkg.com/@phosphor-icons/web"></script>
    
    <!-- Tailwind Configuration -->
    <script>
        tailwind.config = {
            theme: {
                extend: {
                    fontFamily: {
                        sans:['Inter', 'sans-serif'],
                        display:['Space Grotesk', 'sans-serif'],
                    },
                    colors: {
                        brand: {
                            900: '#0a0a0a',
                            800: '#141414',
                            700: '#1f1f1f',
                            accent: '#00ffcc',
                            secondary: '#facc15',
                            journal: '#ff00aa'
                        }
                    },
                    animation: {
                        'pulse-glow': 'pulseGlow 2s infinite',
                    },
                    keyframes: {
                        pulseGlow: {
                            '0%, 100%': { boxShadow: '0 0 0 0 rgba(0, 255, 204, 0.4)' },
                            '50%': { boxShadow: '0 0 0 10px rgba(0, 255, 204, 0)' },
                        }
                    }
                }
            }
        }
    </script>
    
    <!-- Custom Styles -->
    <style>
        body { background-color: #0a0a0a; color: #f5f5f5; overflow-x: hidden; }
        .bg-grid {
            background-size: 40px 40px;
            background-image: linear-gradient(to right, rgba(255, 255, 255, 0.05) 1px, transparent 1px),
                              linear-gradient(to bottom, rgba(255, 255, 255, 0.05) 1px, transparent 1px);
        }
        .btn-journal {
            background-color: rgba(255, 0, 170, 0.1);
            color: #ff00aa;
            border: 1px solid #ff00aa;
            transition: all 0.3s ease;
        }
        .btn-journal:hover {
            background-color: #ff00aa;
            color: #0a0a0a;
            box-shadow: 0 0 20px rgba(255, 0, 170, 0.6);
        }
    </style>
</head>
<body class="bg-brand-900 text-white font-sans antialiased bg-grid selection:bg-brand-accent selection:text-brand-900">

    <!-- Ambient Glows -->
    <div class="fixed inset-0 z-[-1] pointer-events-none">
        <div class="absolute top-[-20%] left-[-10%] w-[500px] h-[500px] bg-brand-accent/10 rounded-full blur-[120px]"></div>
    </div>

    <!-- Navigation (Sama persis dengan index.html) -->
    <nav class="fixed top-0 w-full z-50 bg-brand-900/80 backdrop-blur-md border-b border-brand-700 transition-all duration-300" id="navbar">
        <div class="max-w-7xl mx-auto px-6">
            <div class="flex justify-between h-20 items-center">
                <a href="index.html" class="flex items-center gap-3">
                    <i class="ph-fill ph-globe-hemisphere-east text-3xl text-brand-accent animate-pulse"></i>
                    <span class="font-display font-bold text-xl tracking-tight text-white">ICH <span class="text-brand-accent">Radar</span></span>
                </a>
                
                <div class="hidden lg:flex items-center gap-6">
                    <a href="index.html#about" class="text-sm font-medium text-gray-400 hover:text-brand-accent transition-colors">About</a>
                    <a href="index.html#inventory" class="text-sm font-medium text-gray-400 hover:text-brand-accent transition-colors">Methodology</a>
                    <a href="index.html#capacity-building" class="text-sm font-medium text-gray-400 hover:text-brand-accent transition-colors">Capacity Building</a>
                    <a href="index.html#directives" class="text-sm font-medium text-gray-400 hover:text-brand-accent transition-colors">Directives</a>
                    <a href="index.html#quiz" class="text-sm font-medium text-gray-400 hover:text-brand-secondary transition-colors">Quiz</a>
                </div>

                <div class="flex items-center gap-4">
                    <a href="modul.html" class="hidden sm:flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-bold text-gray-300 border border-brand-700 bg-brand-800 transition-colors" title="Modules for Learning Hub">
                        <i class="ph-fill ph-graduation-cap text-brand-accent text-lg"></i>
                    </a>
                    <a href="book.html" class="hidden sm:flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-bold text-gray-300 border border-brand-700 hover:bg-brand-800 transition-colors" title="Read Content as a Book">
                        <i class="ph-fill ph-book-open text-brand-secondary text-lg"></i>
                    </a>
                    <a href="journal.html" class="hidden sm:flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-bold btn-journal" title="Open Research Journal">
                        <i class="ph-fill ph-notebook text-lg"></i>
                    </a>
                    <a href="radar.html" class="bg-brand-accent hover:bg-[#00e6b8] text-brand-900 px-6 py-2.5 rounded-lg font-bold text-sm transition-all shadow-[0_0_15px_rgba(0,255,204,0.3)] flex items-center gap-2">
                        Launch Radar <i class="ph-bold ph-arrow-right"></i>
                    </a>
                </div>
            </div>
        </div>
    </nav>

    <!-- Hero Section -->
    <header class="relative pt-32 pb-16 lg:pt-40 lg:pb-24 border-b border-brand-700 bg-[#0d0d0d]">
        <div class="max-w-7xl mx-auto px-6 relative z-10 text-center">
            <div class="inline-flex items-center gap-2 px-3 py-1.5 rounded-md bg-brand-800 border border-brand-700 text-brand-accent text-xs font-mono uppercase tracking-widest mb-6">
                <span class="w-2 h-2 rounded-full bg-brand-accent animate-pulse-glow"></span>
                Database Synchronized
            </div>
            <h1 class="text-4xl md:text-6xl font-display font-bold text-white mb-6 tracking-tight">
                Capacity Building <span class="text-transparent bg-clip-text bg-gradient-to-r from-brand-accent to-blue-500">Modules</span>
            </h1>
            <p class="text-gray-400 max-w-2xl mx-auto text-lg leading-relaxed">
                Access official training presentations, analytical models, and operational frameworks directly from the radar system.
            </p>
        </div>
    </header>

    <!-- Grid Katalog Modul -->
    <main class="max-w-7xl mx-auto px-6 py-24 relative z-10">
        <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
            ${modulCards}
        </div>
    </main>

    <!-- Footer Simple -->
    <footer class="border-t border-brand-700 bg-[#0a0a0a] py-8 text-center">
        <div class="max-w-7xl mx-auto px-6">
            <p class="text-xs text-gray-600 font-mono">ICH Radar System &copy; 2026. Data generated automatically.</p>
        </div>
    </footer>

    <!-- Navbar Scroll Logic -->
    <script>
        window.addEventListener('scroll', () => {
            const nav = document.getElementById('navbar');
            if (window.scrollY > 20) {
                nav.classList.add('shadow-lg', 'border-brand-700/50');
            } else {
                nav.classList.remove('shadow-lg', 'border-brand-700/50');
            }
        });
    </script>
</body>
</html>
`;

fs.writeFileSync(modulIndexPath, modulIndexHtml);
console.log('\n✅ SUKSES!');
console.log(`📊 modul.html berhasil di-generate dengan tema UI OSINT (${files.length} dokumen).`);
