# -*- coding: utf-8 -*-

import os
import json
from typing import Optional

import requests
import time
import re
import sys
import subprocess
from urllib.parse import quote
from concurrent.futures import ProcessPoolExecutor
import mutagen
from mutagen.id3 import ID3, TIT2, TPE1, TALB, TRCK, TLEN, APIC
from mutagen.flac import FLAC, Picture
from mutagen.mp3 import MP3

BUF_SIZE = 1024 * 200
WORKERS = int(os.cpu_count() * 1.0)
OUT_DIR = "output"
CACHE_DIR = "cache"
API_SONG_DETAIL_CHUNK_SIZE = 100

global_log = ""


class SongFilename:
    def __init__(self, filename: str):
        self.pname = os.path.splitext(filename)[0]
        self.ext = os.path.splitext(filename)[1]
        self.name = os.path.basename(self.pname)
        self.src_name = {
            '.uc': self.pname,
            '.uc!': self.pname,
            '.nmsf': self.pname.removesuffix('_0'),
        }[self.ext]
        self.name_spilt = self.name.split({
            '.uc': '-',
            '.uc!': '-',
            '.nmsf': '_',
        }[self.ext])
        self.song_id = int(self.name_spilt[0])
        self.song_bitrate = round(int(self.name_spilt[1]) / {
            '.uc': 1,
            '.uc!': 1000,
            '.nmsf': 1000,
        }[self.ext])
        self.song_format = "mp3"
        if self.song_bitrate > 320:
            self.song_format = "flac"

    @property
    def id(self):
        return self.song_id

    @property
    def bitrate(self):
        return self.song_bitrate

    @property
    def ext_est(self):
        return self.song_format


def download_cover_art(session: requests.Session, pic_url: str, song_id: int) -> Optional[str]:
    """Downloads cover art and saves it to CACHE_DIR."""
    if not pic_url:
        return None
    try:
        cover_path = os.path.join(CACHE_DIR, f"{song_id}.jpg")
        if os.path.exists(cover_path):
            return cover_path
        response = session.get(pic_url, timeout=10)
        response.raise_for_status()
        with open(cover_path, 'wb') as f:
            f.write(response.content)
        return cover_path
    except Exception as e:
        p(f"[Error] Failed to download cover for song {song_id}: {e}")
        return None


def get_closest_bitrate(song_detail: dict, song_filename: SongFilename) -> Optional[int]:
    """Finds the closest actual bitrate from song_detail based on nominal bitrate."""
    bitrates_bps = []
    for key in ['sqMusic', 'hrMusic', 'hMusic', 'mMusic', 'lMusic', 'bMusic']:
        music_info = song_detail.get(key)
        if music_info and 'bitrate' in music_info:
            bitrates_bps.append(music_info['bitrate'])
    if not bitrates_bps:
        return None

    target_bps = song_filename.bitrate * 1000
    if song_filename.ext_est == 'mp3':
        closest_bps = min(bitrates_bps, key=lambda x: abs(x - target_bps))
    else:
        bitrates_bps_sq = []
        for bps in bitrates_bps:
            if bps > 320000:
                bitrates_bps_sq.append(bps)
        if bitrates_bps_sq:
            closest_bps = min(bitrates_bps_sq, key=lambda x: abs(x - target_bps))
        else:
            song_filename.song_format = 'mp3'
            closest_bps = min(bitrates_bps, key=lambda x: abs(x - target_bps))
    return closest_bps // 1000  # Return in kbps


def embed_metadata(out_file: str, song_detail: dict, cover_path: Optional[str]):
    """Embeds metadata into the converted audio file."""
    if not song_detail:
        return

    # try:
    _, ext = os.path.splitext(out_file)
    ext = ext.lower()

    title = song_detail.get('name', '')
    artists = [artist['name'] for artist in song_detail.get('artists', [])]
    artist_str = ', '.join(artists) if artists else ''
    album = song_detail.get('album', {}).get('name', '')
    no = str(song_detail.get('no', '1'))
    track_number = f"{song_detail.get('no', '1')}/{song_detail.get('album', {}).get('size', '1')}"
    duration_ms = song_detail.get('duration', 0)

    if ext == '.mp3':
        # Load existing tags or create new ones
        try:
            audio_file = MP3(out_file, ID3=ID3)
        except mutagen.MutagenError:
            try:
                audio_file = MP3(out_file)  # Might fail if no ID3 header (MPEG-MP3)
                audio_file.add_tags()
            except Exception as e:
                print(f"[Info] Skip embedding metadata for MPEG-MP3 file: {out_file} ({e.args})")
                return

        # Set ID3 tags
        audio_file.tags.add(TIT2(encoding=3, text=title))
        audio_file.tags.add(TPE1(encoding=3, text=artist_str))
        audio_file.tags.add(TALB(encoding=3, text=album))
        if track_number:
            audio_file.tags.add(TRCK(encoding=3, text=track_number))
        if duration_ms:
            audio_file.tags.add(TLEN(encoding=3, text=str(duration_ms)))

        # Add cover art
        if cover_path and os.path.exists(cover_path):
            with open(cover_path, 'rb') as img_file:
                audio_file.tags.add(
                    APIC(
                        encoding=3,  # UTF-8
                        mime='image/jpeg',
                        type=3,  # Cover (front)
                        desc='Cover',
                        data=img_file.read()
                    )
                )
        audio_file.save()
        print(f"[Info] Embedded MP3 metadata for: {out_file}")

    elif ext == '.flac':
        audio_file = FLAC(out_file)

        # Set Vorbis Comments
        audio_file['TITLE'] = title
        audio_file['ARTIST'] = artist_str
        audio_file['ALBUM'] = album
        if track_number:
            audio_file['TRACKNUMBER'] = no

        # Add cover art
        if cover_path and os.path.exists(cover_path):
            with open(cover_path, 'rb') as img_file:
                picture = Picture()
                picture.type = 3  # Cover (front)
                picture.desc = 'Cover'
                picture.mime = 'image/jpeg'
                picture.data = img_file.read()
                audio_file.add_picture(picture)

        audio_file.save()
        print(f"[Info] Embedded FLAC metadata for: {out_file}")

    else:
        print(f"[Info] Metadata embedding not implemented for format: {ext}")
    #
    # except Exception as e:
    #     p(f"[Error] Failed to embed metadata into {out_file}: {e}")


def convert_uc(src: str, dest: str):
    """Convert data using XOR."""
    with open(src, 'rb') as fr:
        with open(dest, 'wb') as fw:
            while True:
                buf = fr.read(BUF_SIZE)
                if buf == b'':
                    break
                buf_out = bytearray()
                for b in buf:
                    buf_out.append(b ^ 0xa3)
                fw.write(buf_out)
    mtime = os.path.getmtime(src)
    os.utime(dest, (mtime, mtime))
    print(f"[Info] Converted {src} to {dest} Successfully.")


def convert_file(src_file: str, out_dir: str, song_detail: dict = None):
    song_filename = SongFilename(src_file)
    src_ext = song_filename.ext
    src_name = song_filename.src_name

    # Check bitrate (may refresh output file format)
    bitrate_act = get_closest_bitrate(song_detail, song_filename) or song_filename.bitrate

    # Check file size
    size_matched = True
    try:
        with open(src_name + {
            '.uc': '.idx',
            '.uc!': '.idx!',
            '.nmsf': '.nmsfi',
        }[src_ext]) as f:
            idx = json.load(f)
            if os.path.getsize(src_file) != int(idx[{
                '.uc': 'size',
                '.uc!': 'filesize',
                '.nmsf': 'file_size',
            }[src_ext]]):
                size_matched = False
                print(f"[Info] File: {src_file} Size not match, marked as UNCOMPLETED")
    except Exception as e:
        size_matched = False
        p(f"[Error] Unable to check file size: {e.args}  File: {src_file}")

    # Extract file format
    ext = 'flac'
    try:
        with open(src_name + {
            '.uc': '.info',
            '.uc!': '.idac!',
            '.nmsf': '.config',
        }[src_ext]) as f:
            info = json.load(f)
            ext = info[{
                '.uc': 'format',
                '.uc!': 'audioFormat',
                '.nmsf': 'audioFormat',
            }[src_ext]]
    except FileNotFoundError:
        ext = song_filename.ext_est
    except Exception as e:
        p(f'[Error] Unable to determine file format: {e.args}, assuming it is .{ext}  File: {src_file}')

    # Convert file
    if song_detail and song_detail['name']:
        out_file = f"{song_detail['name']} - {song_detail['artists'][0]['name']}"
        out_file = re.sub(r'[\\/:*?"<>|]', '_', out_file)
    else:
        out_file = song_filename.name
    if size_matched:
        out_file += f' ({bitrate_act}k)'
    else:
        out_file += f' ({bitrate_act}k UNCOMPLETED)'
    out_file += f'.{ext}'
    out_file = os.path.join(out_dir, out_file)
    convert_uc(src_file, out_file)

    # Embed metadata
    cover_path = os.path.join(CACHE_DIR, f"{song_filename.id}.jpg")
    embed_metadata(out_file, song_detail, cover_path)


def get_song_details(song_ids: list[int]) -> list[dict]:
    songs = []
    session = requests.Session()
    for chunk, i in [(song_ids[i:i+API_SONG_DETAIL_CHUNK_SIZE], i) for i in range(0, len(song_ids), API_SONG_DETAIL_CHUNK_SIZE)]:
        print(f"[Info] Getting song details and albums: {i}/{len(song_ids)} {round(i/len(song_ids)*100, 2)}%")
        r = session.get(f'http://music.163.com/api/song/detail/?ids={quote(json.dumps(chunk))}')
        response_data = json.loads(r.text)
        if 'songs' in response_data:
            for j, song in enumerate(response_data['songs']) :
                if song:
                    songs.append(song)
                    pic_url = song.get('album', {}).get('picUrl')
                    if pic_url:
                        _ = download_cover_art(session, pic_url, song['id'])
                        time.sleep(0.05)
                else:
                    p(f"[Error] Song detail not found for song ID: {chunk[j]}")
        else:
             p(f"[Error] Unexpected API response structure for chunk starting at index {i}")
    return songs


def convert_folder(src_dir: str, out_dir=OUT_DIR, workers=WORKERS):
    t0 = time.time()
    print(f'[Info] Workers: {workers}')

    conv_list: list[str] = []
    for root, dirs, files in os.walk(src_dir):
        for file in files:
            filepath = os.path.join(root, file)
            if os.path.splitext(file)[1] in ['.uc', '.uc!', '.nmsf']:
                conv_list.append(filepath)
    print(f"[Info] Added {len(conv_list)} songs")

    songs = {}
    songs_info_list = get_song_details([SongFilename(file).id for file in conv_list])
    for song in songs_info_list:
        songs[song['id']] = song

    with ProcessPoolExecutor(max_workers=workers) as exe:
        for file in conv_list:
            exe.submit(convert_file, file, out_dir, songs.get(SongFilename(file).id, None))
        print("[Info] Concurrent task creation finished. Processing...")

    t1 = time.time()
    print(f'[Info] Done {t1 - t0:.3f}s')


def get_conv_dir() -> str:
    conv_dir: str = ""
    if len(sys.argv) > 1:
        if sys.argv[1] in ['-h', '-help', '--help']:
            print("Usage:\npython convert.py <path-to-cache-folder>\n\nIf cache folder is not specified, it will prompt you to pick a folder")
            exit()
        else:
            conv_dir = sys.argv[1]
    else:
        try:
            import tkinter
            from tkinter import filedialog
            tkinter.Tk().withdraw()
            conv_dir = filedialog.askdirectory()
        except Exception as e:
            p(f"[Error] Unable to open file dialog: {e.args}")
    if not conv_dir:
        conv_dir = input("Enter path to cache folder: ")
    return conv_dir


def p(print_str: str):
    global global_log
    print(print_str)
    global_log += print_str


def log_to_file():
    global global_log
    if global_log:
        print(f"[Info] Logging errors to file...")
        with open(f"{OUT_DIR}/log-{time.strftime('%Y%m%d%H%M%S')}.txt", 'w', encoding='utf-8') as f:
            f.write(global_log)


if __name__ == '__main__':
    os.makedirs(OUT_DIR, exist_ok=True)
    os.makedirs(CACHE_DIR, exist_ok=True)
    cd = get_conv_dir()
    if os.path.exists(cd):
        print(f"[Info] Converting files in: {cd}")
        convert_folder(cd)
        log_to_file()
        try:
            subprocess.Popen(f'explorer "{os.path.abspath(OUT_DIR)}"')
        except Exception as e0:
            p(f"[Error] Cannot open output folder: {e0.args}")
    else:
        p(f"[Error] Folder not found: {cd}")
    input("\nPress enter to exit...\n")
