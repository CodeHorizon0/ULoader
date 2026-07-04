import subprocess, sys, re

def _run(cmd, ffmpeg_path="ffmpeg"):
    creationflags = 0
    if sys.platform.startswith("win"):
        creationflags = subprocess.CREATE_NO_WINDOW

    p = subprocess.Popen(
        [ffmpeg_path] + cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        creationflags=creationflags
    )

    out, err = p.communicate(timeout=15)
    return out, err

def get_hwaccels_all(ffmpeg_path="ffmpeg"):
    out, err = _run(["-hwaccels"], ffmpeg_path)

    lines = (out + "\n" + err).splitlines()

    hw = []
    capture = False

    for line in lines:
        line = line.strip()

        if "Hardware acceleration methods:" in line:
            capture = True
            continue

        if not capture:
            continue

        if not line:
            continue

        if re.match(r"^[a-zA-Z0-9_\-]+$", line):
            hw.append(line)

    return hw

def get_hw_encoders(ffmpeg_path="ffmpeg"):
    out, err = _run(["-encoders"], ffmpeg_path)

    text = (out + "\n" + err)

    encoders = {
        "nvenc": False,
        "qsv": False,
        "amf": False,
        "vaapi": False
    }

    encoders["nvenc"] = bool(re.search(r"\bh264_nvenc\b|\bhevc_nvenc\b", text))
    encoders["qsv"] = bool(re.search(r"\bh264_qsv\b|\bhevc_qsv\b", text))
    encoders["amf"] = bool(re.search(r"\bh264_amf\b|\bhevc_amf\b", text))
    encoders["vaapi"] = bool(re.search(r"\bh264_vaapi\b|\bhevc_vaapi\b", text))

    return encoders

def get_gpu_profile(ffmpeg_path="ffmpeg"):
    hwaccels = set(get_hwaccels_all(ffmpeg_path))
    enc = get_hw_encoders(ffmpeg_path)

    gpu_available = False

    if enc["nvenc"] or enc["qsv"] or enc["amf"] or enc["vaapi"]:
        gpu_available = True

    return {
        "hwaccels": sorted(hwaccels),
        "encoders": enc,
        "gpu_available": gpu_available
    }

def select_best_gpu_encoder(ffmpeg_path="ffmpeg"):
    enc = get_hw_encoders(ffmpeg_path)

    if enc["nvenc"]:
        return "h264_nvenc"
    if enc["qsv"]:
        return "h264_qsv"
    if enc["amf"]:
        return "h264_amf"
    if enc["vaapi"]:
        return "h264_vaapi"

    return None