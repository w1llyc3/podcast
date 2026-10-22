"""Local speech delivery: checked MP3, durable source backup and retry receipt."""
import hashlib
import json
import logging
import os
from pathlib import Path
import shutil
import subprocess

import av
import numpy as np

BIT_RATE = 48000
SAMPLE_RATE = 24000


def _sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1048576), b''):
            digest.update(block)
    return digest.hexdigest()


def _save(path, value):
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(temp, path)


def _inside(path, root):
    path = path.resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError('Audio operation must stay inside the output directory')
    return path


def find_ffmpeg():
    explicit = os.environ.get('PODCAST_FFMPEG')
    if explicit:
        if not Path(explicit).is_file():
            raise RuntimeError('PODCAST_FFMPEG does not point to a file')
        return explicit
    installed = shutil.which('ffmpeg')
    if installed:
        return installed
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except (ImportError, RuntimeError) as exc:
        raise RuntimeError('Install requirements-local.txt or set PODCAST_FFMPEG') from exc


def inspect_audio(path, analyze_channels=False):
    """Decode every frame; do not rely on an advertised container duration."""
    correlations = []
    with av.open(str(path)) as container:
        if len(container.streams.audio) != 1:
            raise RuntimeError('Multiple audio streams require review; original audio retained')
        stream = container.streams.audio[0]
        rate = stream.codec_context.sample_rate
        channels = stream.codec_context.channels
        codec = stream.codec_context.name
        bit_rate = stream.bit_rate
        if channels not in (1, 2):
            raise RuntimeError('Multichannel audio requires review; original audio retained')
        samples = window_samples = 0
        powers = np.zeros(3, dtype=np.float64)
        for frame in container.decode(audio=0):
            samples += frame.samples
            if analyze_channels and channels == 2:
                array = frame.to_ndarray().astype(np.float64)
                left, right = array if frame.format.is_planar else array.reshape(-1, 2).T
                powers += (np.dot(left, left), np.dot(right, right), np.dot(left, right))
                window_samples += frame.samples
                if window_samples >= rate * 60:
                    x, y, xy = powers
                    correlations.append(float(xy / np.sqrt(x*y)) if x*y else (0.0 if x+y else 1.0))
                    powers[:] = 0
                    window_samples = 0
        if window_samples:
            x, y, xy = powers
            correlations.append(float(xy / np.sqrt(x*y)) if x*y else (0.0 if x+y else 1.0))
    if not samples or not rate:
        raise RuntimeError('Decoded audio is empty')
    result = {'duration_seconds': samples/rate, 'codec': codec,
              'sample_rate': rate, 'channels': channels, 'bit_rate': bit_rate,
              'bytes': path.stat().st_size, 'sha256': _sha(path)}
    if analyze_channels:
        # Exclude only opening/closing minute from long recordings; any
        # dissimilar speech window in the body keeps both original channels.
        body = correlations[1:-1] if len(correlations) > 4 else correlations
        duplicated = channels == 1 or (bool(body) and min(body) >= .95)
        result['delivery_channels'] = 1 if duplicated else 2
        result['channel_policy'] = 'mono' if duplicated else 'stereo_preserved_for_review'
        result['minute_correlations'] = correlations
    return result


def is_compressed_audio(info, path):
    compression = info.get('compression', {})
    settings = compression.get('settings', {})
    return (path.suffix.lower() == '.mp3'
            and settings.get('bit_rate') == BIT_RATE
            and settings.get('sample_rate') == SAMPLE_RATE
            and settings.get('channels') in (1, 2)
            and compression.get('validated_full_decode') is True
            and bool(compression.get('source_sha256')))


def ensure_compressed_audio(source, output_root, source_probe, prior_audio=None):
    """Leave source in place until the worker has committed all episode outputs."""
    source = _inside(source, output_root)
    prior_audio = prior_audio or {}
    if is_compressed_audio(prior_audio, source) and _sha(source) == prior_audio.get('sha256'):
        return source, prior_audio
    target = source.parent/'audio.mp3'
    staged = source.parent/'audio.mp3.part'
    receipt_path = source.parent/'audio.compression.json'
    source_sha = _sha(source)
    if receipt_path.exists():
        receipt = json.loads(receipt_path.read_text(encoding='utf-8'))
        info = receipt.get('audio', {})
        settings = info.get('compression', {}).get('settings', {})
        same_source = info.get('compression', {}).get('source_sha256') == source_sha
        same_settings = (settings.get('bit_rate') == BIT_RATE
                         and settings.get('sample_rate') == SAMPLE_RATE)
        if same_source and same_settings and is_compressed_audio(info, target):
            if target.exists() and _sha(target) == info.get('sha256'):
                return target, info
            if staged.exists() and _sha(staged) == info.get('sha256'):
                os.replace(staged, target)
                return target, info
    if target.exists() and target != source:
        raise RuntimeError('Existing MP3 has no matching compression receipt; original retained')
    original = inspect_audio(source, analyze_channels=True)
    backup = _inside(output_root/'.audio-backups'/'automatic'/(source_sha+source.suffix), output_root)
    backup.parent.mkdir(parents=True, exist_ok=True)
    if not backup.exists():
        temporary_backup = backup.with_suffix(backup.suffix+'.tmp')
        shutil.copy2(source, temporary_backup)
        if _sha(temporary_backup) != source_sha:
            raise RuntimeError('Original audio backup checksum mismatch')
        os.replace(temporary_backup, backup)
    if _sha(backup) != source_sha:
        raise RuntimeError('Existing original audio backup checksum mismatch')
    channels = original['delivery_channels']
    if channels == 2:
        logging.warning('Possibly distinct speaker channels; preserving stereo: %s', source)
    subprocess.run([find_ffmpeg(), '-v', 'error', '-xerror', '-nostdin', '-y',
                    '-i', str(source), '-map', '0:a:0', '-map_metadata', '-1', '-vn',
                    '-c:a', 'libmp3lame', '-b:a', '48k', '-ar', '24000',
                    '-ac', str(channels), '-f', 'mp3', str(staged)], check=True)
    encoded = inspect_audio(staged)
    delta = encoded['duration_seconds']-original['duration_seconds']
    if (encoded['codec'] not in ('mp3', 'mp3float')
            or encoded['sample_rate'] != SAMPLE_RATE
            or encoded['channels'] != channels or encoded['bit_rate'] != BIT_RATE
            or abs(delta) > .25):
        raise RuntimeError('Compressed audio failed codec, channel or duration validation')
    if _sha(source) != source_sha:
        raise RuntimeError('Original audio changed during compression')
    encoded['container'] = 'mp3'
    encoded['compression'] = {
        'source_sha256': source_sha, 'source_filename': source.name,
        'source_bytes': original['bytes'],
        'source_duration_seconds': source_probe['duration_seconds'],
        'original_backup': str(backup), 'validated_full_decode': True,
        'duration_difference_seconds': delta, 'channel_policy': original['channel_policy'],
        'settings': {'format': 'MP3', 'bit_rate': BIT_RATE,
                     'sample_rate': SAMPLE_RATE, 'channels': channels}}
    # Save expected bytes before promoting the staged file so a crash between
    # these two writes can be recovered without encoding a second generation.
    _save(receipt_path, {'audio': encoded})
    os.replace(staged, target)
    return target, encoded


def cleanup_original(target, info, output_root):
    compression = info.get('compression', {})
    filename = compression.get('source_filename')
    if not filename:
        return
    source = _inside(target.parent/filename, output_root)
    if source == target or not source.exists():
        return
    backup = _inside(Path(compression['original_backup']), output_root)
    if (_sha(backup) != compression['source_sha256']
            or _sha(source) != compression['source_sha256']
            or _sha(target) != info['sha256']):
        raise RuntimeError('Refusing to remove original: audio checksum mismatch')
    source.unlink()
