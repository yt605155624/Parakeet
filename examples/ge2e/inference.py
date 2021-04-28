import argparse
from pathlib import Path

import tqdm
import paddle
import numpy as np

from parakeet.models.lstm_speaker_encoder import LSTMSpeakerEncoder

from audio_processor import SpeakerVerificationPreprocessor
from config import get_cfg_defaults


def embed_utterance(processor, model, fpath_or_wav):
    # audio processor
    wav = processor.preprocess_wav(fpath_or_wav)
    mel_partials = processor.extract_mel_partials(wav)

    model.eval()
    # speaker encoder
    with paddle.no_grad():
        mel_partials = paddle.to_tensor(mel_partials)
        with paddle.no_grad():
            embed = model.embed_utterance(mel_partials)
    embed = embed.numpy()
    return embed


def _process_utterance(ifpath: Path, input_dir: Path, output_dir: Path,
                       processor: SpeakerVerificationPreprocessor,
                       model: LSTMSpeakerEncoder):
    rel_path = ifpath.relative_to(input_dir)
    ofpath = (output_dir / rel_path).with_suffix(".npy")
    ofpath.parent.mkdir(parents=True, exist_ok=True)
    embed = embed_utterance(processor, model, ifpath)
    np.save(ofpath, embed)


def main(config, args):
    paddle.set_device(args.device)

    # load model
    model = LSTMSpeakerEncoder(config.data.n_mels, config.model.num_layers,
                               config.model.hidden_size,
                               config.model.embedding_size)
    weights_fpath = str(Path(args.checkpoint_path).expanduser())
    model_state_dict = paddle.load(weights_fpath + ".pdparams")
    model.set_state_dict(model_state_dict)
    model.eval()
    print(f"Loaded encoder {weights_fpath}")

    # create audio processor
    c = config.data
    processor = SpeakerVerificationPreprocessor(
        sampling_rate=c.sampling_rate,
        audio_norm_target_dBFS=c.audio_norm_target_dBFS,
        vad_window_length=c.vad_window_length,
        vad_moving_average_width=c.vad_moving_average_width,
        vad_max_silence_length=c.vad_max_silence_length,
        mel_window_length=c.mel_window_length,
        mel_window_step=c.mel_window_step,
        n_mels=c.n_mels,
        partial_n_frames=c.partial_n_frames,
        min_pad_coverage=c.min_pad_coverage,
        partial_overlap_ratio=c.min_pad_coverage,
    )

    # input output preparation
    input_dir = Path(args.input).expanduser()
    ifpaths = list(input_dir.rglob(args.pattern))
    print(f"{len(ifpaths)} utterances in total")
    output_dir = Path(args.output).expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)

    for ifpath in tqdm.tqdm(ifpaths, unit="utterance"):
        _process_utterance(ifpath, input_dir, output_dir, processor, model)


if __name__ == "__main__":
    config = get_cfg_defaults()
    parser = argparse.ArgumentParser(description="compute utterance embed.")
    parser.add_argument(
        "--config",
        metavar="FILE",
        help="path of the config file to overwrite to default config with.")
    parser.add_argument("--input",
                        type=str,
                        help="path of the audio_file folder.")
    parser.add_argument("--pattern",
                        type=str,
                        default="*.wav",
                        help="pattern to filter audio files.")
    parser.add_argument("--output",
                        metavar="OUTPUT_DIR",
                        help="path to save checkpoint and logs.")

    # load from saved checkpoint
    parser.add_argument("--checkpoint_path",
                        type=str,
                        help="path of the checkpoint to load")

    # running
    parser.add_argument("--device",
                        type=str,
                        choices=["cpu", "gpu"],
                        help="device type to use, cpu and gpu are supported.")

    # overwrite extra config and default config
    parser.add_argument(
        "--opts",
        nargs=argparse.REMAINDER,
        help=
        "options to overwrite --config file and the default config, passing in KEY VALUE pairs"
    )

    args = parser.parse_args()
    if args.config:
        config.merge_from_file(args.config)
    if args.opts:
        config.merge_from_list(args.opts)
    config.freeze()
    print(config)
    print(args)

    main(config, args)
