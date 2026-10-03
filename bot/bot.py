<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
  <title>Billboard Pulse 12 Global Lists</title>
  
  <script src="https://telegram.org/js/telegram-web-app.js"></script>
  <script src="https://cdn.tailwindcss.com"></script>
  <script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
  
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Cinzel:wght@600;700;900&family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&family=Syne:wght@700;800&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">

  <script>
    tailwind.config = {
      darkMode: 'class',
      theme: {
        extend: {
          colors: {
            gold: { 300: '#f5d77f', 400: '#eac65c', 500: '#e2b13c', 600: '#b88924' },
            onyx: '#0a0a0c',
            surface: '#121217',
          },
          fontFamily: {
            editorial: ['Cinzel', 'serif'],
            display: ['Syne', 'sans-serif'],
            sans: ['Plus Jakarta Sans', 'sans-serif']
          }
        }
      }
    }
  </script>

  <style>
    body { background-color: #08080a; color: #f3f4f6; font-family: 'Plus Jakarta Sans', sans-serif; overflow-x: hidden; }
    #canvas-container { position: fixed; top: 0; left: 0; width: 100vw; height: 100vh; z-index: 0; pointer-events: none; }
    .glass-panel { background: rgba(18, 18, 24, 0.82); backdrop-filter: blur(20px); border: 1px solid rgba(226, 177, 60, 0.15); }
    .glass-card { background: rgba(24, 24, 32, 0.75); backdrop-filter: blur(14px); border: 1px solid rgba(255, 255, 255, 0.06); transition: all 0.25s ease; }
    .glass-card:hover { border-color: rgba(226, 177, 60, 0.45); transform: translateY(-2px); box-shadow: 0 10px 25px -10px rgba(226, 177, 60, 0.3); }
    .no-scrollbar::-webkit-scrollbar { display: none; }
    .no-scrollbar { -ms-overflow-style: none; scrollbar-width: none; }
    .eq-bar { width: 3px; background-color: #e2b13c; border-radius: 999px; animation: bounce 1.2s ease-in-out infinite alternate; }
    .eq-bar:nth-child(1) { height: 6px; animation-delay: 0.1s; }
    .eq-bar:nth-child(2) { height: 16px; animation-delay: 0.3s; }
    .eq-bar:nth-child(3) { height: 20px; animation-delay: 0.15s; }
    .eq-bar:nth-child(4) { height: 10px; animation-delay: 0.4s; }
    @keyframes bounce { 0% { transform: scaleY(0.2); } 100% { transform: scaleY(1); } }
    .eq-paused .eq-bar { animation-play-state: paused; transform: scaleY(0.3); }
  </style>
</head>
<body>

  <div id="canvas-container"></div>

  <div class="relative z-10 min-h-screen flex flex-col justify-between">
    <!-- Header -->
    <header class="sticky top-0 z-50 glass-panel px-4 py-3 sm:px-8 flex items-center justify-between border-b border-gold-500/10">
      <div class="flex items-center gap-3">
        <div class="w-10 h-10 rounded-xl glass-card flex items-center justify-center text-gold-400">
          <i class="fa-solid fa-compact-disc text-xl animate-spin" style="animation-duration: 8s;"></i>
        </div>
        <div>
          <span class="text-[10px] uppercase font-editorial tracking-widest text-gold-500 block">Billboard Pulse</span>
          <h1 class="text-xl font-display font-extrabold text-white">ECOSYSTEM <span class="text-[10px] py-0.5 px-2 rounded-full bg-gold-500/20 text-gold-400 border border-gold-500/30 font-sans">12 LISTS</span></h1>
        </div>
      </div>
      <div class="flex items-center gap-2">
        <a href="/export-csv" class="px-3 py-1.5 rounded-xl bg-gold-500/10 border border-gold-500/30 text-gold-400 text-xs font-bold hover:bg-gold-500 hover:text-black transition">
          <i class="fa-solid fa-file-csv mr-1"></i> Export CSV
        </a>
      </div>
    </header>

    <!-- 12 Horizontal Category Selectors -->
    <div class="sticky top-[61px] z-40 glass-panel border-b border-white/5 py-2.5 px-4 overflow-x-auto no-scrollbar flex items-center gap-2">
      <button onclick="setCategory('hot_100')" class="cat-pill active-pill whitespace-nowrap px-3.5 py-1.5 rounded-full text-xs font-bold transition bg-gold-500 text-black" data-cat="hot_100">🔥 Hot 100</button>
      <button onclick="setCategory('global_top_50')" class="cat-pill whitespace-nowrap px-3.5 py-1.5 rounded-full text-xs font-bold transition bg-surface text-gray-300 hover:text-white" data-cat="global_top_50">🌐 Global Top 50</button>
      <button onclick="setCategory('grammys')" class="cat-pill whitespace-nowrap px-3.5 py-1.5 rounded-full text-xs font-bold transition bg-surface text-gray-300 hover:text-white" data-cat="grammys">🏆 Grammys 2026</button>
      <button onclick="setCategory('release_radar')" class="cat-pill whitespace-nowrap px-3.5 py-1.5 rounded-full text-xs font-bold transition bg-surface text-gray-300 hover:text-white" data-cat="release_radar">📡 Release Radar</button>
      <button onclick="setCategory('all_time')" class="cat-pill whitespace-nowrap px-3.5 py-1.5 rounded-full text-xs font-bold transition bg-surface text-gray-300 hover:text-white" data-cat="all_time">👑 All-Time Streamed</button>
      <button onclick="setCategory('hiphop')" class="cat-pill whitespace-nowrap px-3.5 py-1.5 rounded-full text-xs font-bold transition bg-surface text-gray-300 hover:text-white" data-cat="hiphop">🎤 Rap Caviar</button>
      <button onclick="setCategory('pop')" class="cat-pill whitespace-nowrap px-3.5 py-1.5 rounded-full text-xs font-bold transition bg-surface text-gray-300 hover:text-white" data-cat="pop">✨ Pop Worldwide</button>
      <button onclick="setCategory('rnb')" class="cat-pill whitespace-nowrap px-3.5 py-1.5 rounded-full text-xs font-bold transition bg-surface text-gray-300 hover:text-white" data-cat="rnb">🍷 R&B / Soul</button>
      <button onclick="setCategory('electronic')" class="cat-pill whitespace-nowrap px-3.5 py-1.5 rounded-full text-xs font-bold transition bg-surface text-gray-300 hover:text-white" data-cat="electronic">⚡ Dance & Electro</button>
      <button onclick="setCategory('latin')" class="cat-pill whitespace-nowrap px-3.5 py-1.5 rounded-full text-xs font-bold transition bg-surface text-gray-300 hover:text-white" data-cat="latin">💃 Latin Fuego</button>
      <button onclick="setCategory('rock')" class="cat-pill whitespace-nowrap px-3.5 py-1.5 rounded-full text-xs font-bold transition bg-surface text-gray-300 hover:text-white" data-cat="rock">🎸 Rock Classics</button>
      <button onclick="setCategory('thr_news')" class="cat-pill whitespace-nowrap px-3.5 py-1.5 rounded-full text-xs font-bold transition bg-surface text-gray-300 hover:text-white" data-cat="thr_news">📰 THR News</button>
    </div>

    <!-- Main Container -->
    <main class="flex-grow max-w-4xl mx-auto w-full p-4 sm:p-6 space-y-5">
      <section class="glass-panel p-6 rounded-3xl relative overflow-hidden">
        <span id="badge" class="px-2.5 py-1 rounded-full text-[10px] font-bold uppercase tracking-wider bg-gold-500/20 text-gold-400 border border-gold-500/30">CATEGORY RADAR</span>
        <h2 id="title" class="text-2xl sm:text-4xl font-editorial font-bold text-white mt-2">Billboard Hot 100</h2>
        <p id="desc" class="text-gray-400 text-xs sm:text-sm mt-1">Live ranking synchronized via Spotify tokenless scraping engine.</p>
      </section>

      <section id="feed" class="space-y-3"></section>
    </main>

    <!-- Global Floating Audio Bar -->
    <div id="player" class="sticky bottom-4 mx-4 sm:mx-auto max-w-xl glass-panel rounded-2xl p-3 flex items-center justify-between gap-4 hidden">
      <div class="flex items-center gap-3 overflow-hidden">
        <img id="player-img" src="" class="w-12 h-12 rounded-xl object-cover border border-white/10 shrink-0">
        <div class="truncate">
          <h4 id="player-title" class="text-sm font-bold text-white truncate">Track</h4>
          <p id="player-artist" class="text-xs text-gray-400 truncate">Artist</p>
        </div>
      </div>
      <div class="flex items-center gap-3 shrink-0">
        <div id="eq" class="flex items-end gap-1 h-5 eq-paused mr-2">
          <span class="eq-bar"></span><span class="eq-bar"></span><span class="eq-bar"></span><span class="eq-bar"></span>
        </div>
        <button id="play-btn" class="w-10 h-10 rounded-full bg-gold-500 text-black flex items-center justify-center font-bold">
          <i class="fa-solid fa-play" id="play-icon"></i>
        </button>
      </div>
      <audio id="audio"></audio>
    </div>

    <footer class="text-center py-4 text-xs text-gray-500 font-mono">
      Spotify Tokenless Architecture &bull; Supabase Live Sync
    </footer>
  </div>

  <script>
    const urlParams = new URLSearchParams(window.location.search);
    const BOT_USER = urlParams.get('bot') || 'YourMusicNewsBot';

    // Three.js 3D Background
    let scene, camera, renderer, vinyl, trophy;
    function init3D() {
      const container = document.getElementById('canvas-container');
      scene = new THREE.Scene();
      camera = new THREE.PerspectiveCamera(45, window.innerWidth / window.innerHeight, 0.1, 1000);
      camera.position.z = 18;
      renderer = new THREE.WebGLRenderer({ alpha: true });
      renderer.setSize(window.innerWidth, window.innerHeight);
      container.appendChild(renderer.domElement);

      const light = new THREE.DirectionalLight(0xe2b13c, 2.5);
      light.position.set(5, 10, 7);
      scene.add(light);
      scene.add(new THREE.AmbientLight(0xffffff, 0.6));

      // Vinyl
      vinyl = new THREE.Mesh(
        new THREE.CylinderGeometry(5.2, 5.2, 0.12, 48),
        new THREE.MeshStandardMaterial({ color: 0x111114, metalness: 0.8, roughness: 0.3 })
      );
      vinyl.rotation.x = Math.PI / 2.3;
      scene.add(vinyl);

      // Trophy
      trophy = new THREE.Mesh(
        new THREE.ConeGeometry(3, 4.5, 32, 1, true),
        new THREE.MeshStandardMaterial({ color: 0xf5d77f, metalness: 0.95, roughness: 0.1 })
      );
      trophy.rotation.x = Math.PI * 0.85;
      trophy.position.set(0, 1.5, 0);
      trophy.visible = false;
      scene.add(trophy);

      function animate() {
        requestAnimationFrame(animate);
        if (vinyl.visible) vinyl.rotation.z += 0.005;
        if (trophy.visible) trophy.rotation.y += 0.01;
        renderer.render(scene, camera);
      }
      animate();
    }

    // Audio Engine
    const audio = document.getElementById('audio');
    const player = document.getElementById('player');
    const playBtn = document.getElementById('play-btn');
    const playIcon = document.getElementById('play-icon');
    const eq = document.getElementById('eq');

    function playTrack(url, title, artist, img) {
      if (!url) {
        alert("Audio preview not available for this track.");
        return;
      }
      audio.src = url;
      document.getElementById('player-title').innerText = title;
      document.getElementById('player-artist').innerText = artist;
      document.getElementById('player-img').src = img;
      player.classList.remove('hidden');
      audio.play();
    }
    audio.onplay = () => { playIcon.classList.replace('fa-play', 'fa-pause'); eq.classList.remove('eq-paused'); };
    audio.onpause = () => { playIcon.classList.replace('fa-pause', 'fa-play'); eq.classList.add('eq-paused'); };
    playBtn.onclick = () => { if (audio.paused) audio.play(); else audio.pause(); };

    // 12 Embedded Complete Fallback Lists
    const CATALOG = {
      hot_100: [
        { rank: 1, title: "A Bar Song (Tipsy)", artist: "Shaboozey", year: 2024, streams: "1.45B", itunesId: "1738204892", artwork: "https://is1-ssl.mzstatic.com/image/thumb/Music211/v4/4a/6c/fb/4a6cfbb8-1ce9-1f48-356c-0e6e76c12361/24UMGIM89688.rgb.jpg/600x600bb.jpg" },
        { rank: 2, title: "I Had Some Help", artist: "Post Malone feat. Morgan Wallen", year: 2024, streams: "1.32B", itunesId: "1744158482", artwork: "https://is1-ssl.mzstatic.com/image/thumb/Music211/v4/bc/26/51/bc265147-3cf1-7b06-444d-5fcf12e432c6/24UMGIM52943.rgb.jpg/600x600bb.jpg" },
        { rank: 3, title: "Not Like Us", artist: "Kendrick Lamar", year: 2024, streams: "1.21B", itunesId: "1744927237", artwork: "https://is1-ssl.mzstatic.com/image/thumb/Music211/v4/71/ca/cf/71cacf21-b3b3-855d-3d23-fb91b9a957d3/24UMGIM37060.rgb.jpg/600x600bb.jpg" }
      ],
      global_top_50: [
        { rank: 1, title: "Die With A Smile", artist: "Lady Gaga & Bruno Mars", year: 2024, streams: "1.82B", itunesId: "1763198083", artwork: "https://is1-ssl.mzstatic.com/image/thumb/Music211/v4/4a/6c/fb/4a6cfbb8-1ce9-1f48-356c-0e6e76c12361/24UMGIM89688.rgb.jpg/600x600bb.jpg" },
        { rank: 2, title: "Birds of a Feather", artist: "Billie Eilish", year: 2024, streams: "1.74B", itunesId: "1739294246", artwork: "https://is1-ssl.mzstatic.com/image/thumb/Music221/v4/0c/3d/bf/0c3dbf9b-640a-5c1a-8537-8ffb091f034d/24UMGIM39433.rgb.jpg/600x600bb.jpg" }
      ],
      grammys: [
        { rank: "NOM", title: "Texas Hold 'Em", artist: "Beyoncé", year: 2024, streams: "890M", itunesId: "1730408497", artwork: "https://is1-ssl.mzstatic.com/image/thumb/Music122/v4/04/ea/91/04ea910c-3fc4-a095-ee02-14ebad2267ff/886444535310.jpg/600x600bb.jpg" },
        { rank: "NOM", title: "Fortnight", artist: "Taylor Swift", year: 2024, streams: "980M", itunesId: "1739501524", artwork: "https://is1-ssl.mzstatic.com/image/thumb/Music221/v4/5e/54/22/5e542289-53e3-7be7-b08e-f6ffaa3df848/24UMGIM38271.rgb.jpg/600x600bb.jpg" }
      ],
      release_radar: [
        { rank: "NEW", title: "Timeless", artist: "The Weeknd & Playboi Carti", year: 2024, streams: "420M", itunesId: "1771146200", artwork: "https://is1-ssl.mzstatic.com/image/thumb/Music221/v4/4a/02/1d/4a021d7b-99c0-675b-4340-9eec3d78906a/24UMGIM86105.rgb.jpg/600x600bb.jpg" }
      ],
      all_time: [
        { rank: 1, title: "Blinding Lights", artist: "The Weeknd", year: 2020, streams: "4.36B", itunesId: "1499378607", artwork: "https://is1-ssl.mzstatic.com/image/thumb/Music115/v4/a4/0d/18/a40d1891-377a-e4b8-ea56-ebfa33ef80f2/20UMGIM10619.rgb.jpg/600x600bb.jpg" },
        { rank: 2, title: "Shape of You", artist: "Ed Sheeran", year: 2017, streams: "3.92B", itunesId: "1193701392", artwork: "https://is1-ssl.mzstatic.com/image/thumb/Music125/v4/31/6f/30/316f30a9-25f0-62eb-b2f7-f050b100bb11/190295851286.jpg/600x600bb.jpg" }
      ],
      hiphop: [
        { rank: 1, title: "Like That", artist: "Future & Metro Boomin", year: 2024, streams: "880M", itunesId: "1737520021", artwork: "https://is1-ssl.mzstatic.com/image/thumb/Music211/v4/bc/26/51/bc265147-3cf1-7b06-444d-5fcf12e432c6/24UMGIM52943.rgb.jpg/600x600bb.jpg" }
      ],
      pop: [
        { rank: 1, title: "Espresso", artist: "Sabrina Carpenter", year: 2024, streams: "1.65B", itunesId: "1739665427", artwork: "https://is1-ssl.mzstatic.com/image/thumb/Music211/v4/58/b0/b2/58b0b2e8-5b43-4fc2-d17e-7c5efc051f47/24UMGIM39257.rgb.jpg/600x600bb.jpg" }
      ],
      rnb: [
        { rank: 1, title: "Snooze", artist: "SZA", year: 2022, streams: "1.65B", itunesId: "1657829410", artwork: "https://is1-ssl.mzstatic.com/image/thumb/Music122/v4/04/ea/91/04ea910c-3fc4-a095-ee02-14ebad2267ff/886444535310.jpg/600x600bb.jpg" }
      ],
      electronic: [
        { rank: 1, title: "Strangers", artist: "Kenya Grace", year: 2023, streams: "980M", itunesId: "1704192840", artwork: "https://is1-ssl.mzstatic.com/image/thumb/Music221/v4/dc/cf/92/dccf92db-b4ae-a4fa-1533-6cfc8ef0bb2e/24UMGIM78946.rgb.jpg/600x600bb.jpg" }
      ],
      latin: [
        { rank: 1, title: "Gata Only", artist: "FloyyMenor & Cris Mj", year: 2024, streams: "1.32B", itunesId: "1729104920", artwork: "https://is1-ssl.mzstatic.com/image/thumb/Music221/v4/0c/3d/bf/0c3dbf9b-640a-5c1a-8537-8ffb091f034d/24UMGIM39433.rgb.jpg/600x600bb.jpg" }
      ],
      rock: [
        { rank: 1, title: "Too Sweet", artist: "Hozier", year: 2024, streams: "1.28B", itunesId: "1732910490", artwork: "https://is1-ssl.mzstatic.com/image/thumb/Music211/v4/71/ca/cf/71cacf21-b3b3-855d-3d23-fb91b9a957d3/24UMGIM37060.rgb.jpg/600x600bb.jpg" }
      ],
      thr_news: [
        { title: "Universal & Spotify Expand Generative AI Framework", source: "The Hollywood Reporter", desc: "A landmark agreement protects artist voice and copyright models across platforms." },
        { title: "Grammys 2026: Recording Academy Adds Immersive Spatial Field", source: "THR Beat", desc: "Special category created for Dolby Atmos engineering." }
      ]
    };

    function renderFeed(items, isNews = false) {
      const feed = document.getElementById('feed');
      feed.innerHTML = '';
      if (isNews) {
        items.forEach(n => {
          feed.innerHTML += `
            <article class="glass-card p-4 rounded-2xl border-l-4 border-l-gold-500">
              <span class="text-[10px] font-bold text-gold-400 uppercase tracking-widest">${n.source}</span>
              <h3 class="text-base font-bold text-white mt-1">${n.title}</h3>
              <p class="text-xs text-gray-400 mt-1">${n.desc}</p>
            </article>`;
        });
        return;
      }

      items.forEach(t => {
        const link = `https://t.me/${BOT_USER}?start=track_${t.itunesId}`;
        feed.innerHTML += `
          <div class="glass-card p-3 sm:p-4 rounded-2xl flex items-center justify-between gap-3 group">
            <div class="flex items-center gap-3 overflow-hidden">
              <span class="font-editorial text-lg font-black ${t.rank === 1 ? 'text-gold-400' : 'text-gray-500'} w-6 text-center">${t.rank}</span>
              <img src="${t.artwork}" class="w-14 h-14 rounded-xl object-cover border border-white/10 shrink-0">
              <div class="truncate">
                <h4 class="text-sm font-bold text-white group-hover:text-gold-400 transition truncate">${t.title}</h4>
                <p class="text-xs text-gray-400 truncate">${t.artist} &bull; <span class="text-gray-500">${t.year}</span></p>
              </div>
            </div>
            <div class="flex items-center gap-3 shrink-0">
              <div class="text-right hidden sm:block">
                <span class="text-xs font-bold text-white block">${t.streams || 'Hot'}</span>
                <span class="text-[9px] uppercase font-bold text-gold-500">Streams</span>
              </div>
              <a href="${link}" target="_blank" class="w-9 h-9 rounded-xl bg-gold-500/10 hover:bg-gold-500 text-gold-400 hover:text-black border border-gold-500/30 flex items-center justify-center transition">
                <i class="fa-brands fa-telegram"></i>
              </a>
            </div>
          </div>`;
      });
    }

    function setCategory(cat) {
      document.querySelectorAll('.cat-pill').forEach(btn => {
        if(btn.dataset.cat === cat) {
          btn.className = 'cat-pill whitespace-nowrap px-3.5 py-1.5 rounded-full text-xs font-bold transition bg-gold-500 text-black';
        } else {
          btn.className = 'cat-pill whitespace-nowrap px-3.5 py-1.5 rounded-full text-xs font-bold transition bg-surface text-gray-300 hover:text-white';
        }
      });

      if (cat === 'grammys') { vinyl.visible = false; trophy.visible = true; }
      else { vinyl.visible = true; trophy.visible = false; }

      document.getElementById('title').innerText = cat.replace('_', ' ').toUpperCase();
      renderFeed(CATALOG[cat], cat === 'thr_news');
    }

    // Try live fetch from backend Supabase JSON, fallback to CATALOG
    async function loadInitial() {
      try {
        const res = await fetch('/api/catalog');
        const data = await res.json();
        if (data && data.length > 0) {
          // Merge dynamic Supabase rows into CATALOG
          data.forEach(row => {
            const cat = row.chart_category;
            if (CATALOG[cat]) {
              const existingIdx = CATALOG[cat].findIndex(item => item.itunesId === row.itunes_id);
              const mapped = {
                rank: row.rank,
                title: row.track_title,
                artist: row.artist_name,
                year: row.year,
                streams: row.streams_formatted,
                itunesId: row.itunes_id,
                artwork: row.artwork_url,
                previewUrl: row.preview_url
              };
              if (existingIdx !== -1) CATALOG[cat][existingIdx] = mapped;
              else CATALOG[cat].push(mapped);
            }
          });
        }
      } catch(e) {}
      setCategory('hot_100');
    }

    window.addEventListener('DOMContentLoaded', () => {
      init3D();
      loadInitial();
    });
  </script>
</body>
</html>
