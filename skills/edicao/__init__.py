from pipeline.models import EditOutput, ImagesOutput
from pipeline.providers.media import concatenate, render_scene
from pipeline.skill import Context, Skill
from pipeline.storage import artifact, inside, write_json


class Edicao(Skill):
    name = "edicao"
    input_model = ImagesOutput
    output_model = EditOutput

    def execute(self, previous: ImagesOutput, context: Context) -> dict:
        cfg = context.config.editing
        assets = {a.scene_id: a for a in previous.assets.items}
        audio = {s.section_id: s for s in previous.narration.segments}
        clips, timeline = [], []
        offset = 0.0
        previous_frame = 0
        for section in previous.script.sections:
            scenes = [s for s in previous.visual_plan.scenes if s.section_id == section.id]
            segment = audio[section.id]
            total_weight = sum(s.weight for s in scenes)
            start = 0.0
            for scene in scenes:
                seconds = segment.duration_seconds * scene.weight / total_weight
                end_frame = round((offset + start + seconds) * cfg.fps)
                frames = end_frame - previous_frame
                if frames < 1:
                    raise ValueError(
                        f"Scene {scene.id} is shorter than one video frame; reduce scene count"
                    )
                clip = context.path(f"assets/edicao/{scene.id}.mp4")
                visual = assets[scene.id].media
                render_scene(inside(context.root, visual.path), clip, frames, visual.kind, cfg)
                clips.append(clip)
                timeline.append(
                    {
                        "scene_id": scene.id,
                        "section_id": section.id,
                        "start_seconds": previous_frame / cfg.fps,
                        "duration_seconds": frames / cfg.fps,
                        "narration_start_seconds": offset + start,
                    }
                )
                start += seconds
                previous_frame = end_frame
            offset += segment.duration_seconds
        target = context.path("final.demo.mp4" if context.demo else "final.mp4")
        narration = [inside(context.root, s.audio.path) for s in previous.narration.segments]
        info = concatenate(clips, narration, context.root / "assets/edicao", target, cfg, offset)
        video_stream = next(s for s in info["streams"] if s["codec_type"] == "video")
        write_json(context.path("timeline.json"), timeline)
        return {
            **previous.model_dump(mode="json"),
            "video": {
                "file": artifact(context.root, target, "video").model_dump(),
                "duration_seconds": float(info["format"]["duration"]),
                "width": video_stream["width"],
                "height": video_stream["height"],
                "demo": context.demo,
            },
        }
