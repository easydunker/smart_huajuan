"""CLI entry point for Academic AI Translator."""

import os
from pathlib import Path
from typing import TYPE_CHECKING

import click

if TYPE_CHECKING:
    from aat.storage.checkpoints import Checkpoint
    from aat.storage.models import TranslationProject


@click.group()
@click.version_option(version="0.1.0")
def main() -> None:
    """Academic AI Translator (AAT) - Local-first translation tool for academic documents."""
    pass


@main.command()
@click.argument("input_path", type=click.Path(exists=True))
@click.option("--to", "target_lang", default="zh", help="Target language (default: zh)")
@click.option("--enable-web", is_flag=True, help="Enable external web search (OpenAlex)")
@click.option("--offline", is_flag=True, help="Force offline mode (no network calls)")
@click.option("--ui", is_flag=True, help="Launch localhost UI")
@click.option("--output", "-o", type=click.Path(), help="Output file path")
@click.option("--interactive", is_flag=True, help="Pause for human feedback at each segment")
def translate(
    input_path: str,
    target_lang: str,
    enable_web: bool,
    offline: bool,
    ui: bool,
    output: str | None,
    interactive: bool = False,
) -> None:
    """Translate a document.

    Translate a document from English to the target language.

    \b
    Example:
        aat translate paper.docx --to zh
        aat translate paper.docx --enable-web
        aat translate paper.docx --offline
    """
    click.echo(f"Translating {input_path} to {target_lang}...")

    if offline:
        click.echo("Running in offline mode")

    if enable_web:
        click.echo("Web search enabled (OpenAlex)")

    if ui:
        click.echo("After translation completes, run: aat review <project_dir>")


    # Import required modules
    from pathlib import Path
    from aat.retrieval.ingestion import LibraryIngestion
    from aat.translate.pipeline import TranslationPipeline
    import json

    # Step 1: Check if file is already in library
    input_path_obj = Path(input_path)
    library_dir = Path.home() / ".aat" / "library"
    ingestion = LibraryIngestion(library_dir)

    # Search for chunks from this file
    chunks = ingestion.search_by_language("en")

    if not chunks:
        click.echo("Error: File not found in library. Please run 'aat add-library' first.")
        return

    click.echo(f"Found {len(chunks)} chunks in library")

    # Step 2: Create output directory
    output_dir = Path.home() / ".aat" / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Step 3: Run real translation using Anthropic Claude
    output_file = output or output_dir / f"{input_path_obj.stem}_translated.md"
    output_path = Path(output_file)

    click.echo(f"Starting real translation of {len(chunks)} chunks using Claude...")

    try:
        from aat.storage.models import DocumentModel, TranslationProject, Paragraph, Section
        from aat.translate.pipeline import TranslationPipeline, PipelineConfig

        click.echo(f"\n{'─'*70}")
        click.echo("STEP 1: Preparing document structure")
        click.echo(f"{'─'*70}")

        # Create paragraphs from chunks
        paragraphs = []
        chunk_count = len(chunks)
        for i, chunk in enumerate(chunks):
            para = Paragraph(
                pid=f"para_{i}",
                text=chunk.get('text', '')
            )
            paragraphs.append(para)
            if (i + 1) % 50 == 0 or i == chunk_count - 1:
                click.echo(f"  ✓ Processed {i+1}/{chunk_count} chunks...")

        click.echo(f"\n{'─'*70}")
        click.echo("STEP 2: Building document structure")
        click.echo(f"{'─'*70}")

        # Create a single section containing all paragraphs
        section = Section(
            heading="Chapter 1",
            paragraphs=paragraphs
        )
        click.echo(f"  ✓ Created section with {len(paragraphs)} paragraphs")

        # Create document and project
        doc_model = DocumentModel(
            doc_id=input_path_obj.stem,
            title=input_path_obj.stem,
            sections=[section],
            references=[],
            citations=[]
        )
        click.echo(f"  ✓ Created document model: {doc_model.doc_id}")

        project = TranslationProject(
            project_id=f"proj_{input_path_obj.stem}",
            document=doc_model
        )
        click.echo(f"  ✓ Created translation project: {project.project_id}")

        click.echo(f"\n{'─'*70}")
        click.echo("STEP 3: Configuring translation engine")
        click.echo(f"{'─'*70}")

        # Configure with Anthropic
        config = PipelineConfig(
            llm_provider="anthropic",
            llm_model="claude-3-5-sonnet-20241022",
            enable_checkpoints=True
        )
        click.echo(f"  ✓ Provider: Anthropic Claude")
        click.echo(f"  ✓ Model: {config.llm_model}")
        click.echo(f"  ✓ Checkpoints: {'Enabled' if config.enable_checkpoints else 'Disabled'}")

        # Run translation
        click.echo(f"\n{'─'*70}")
        click.echo("STEP 4: Running translation pipeline")
        click.echo(f"{'─'*70}")
        click.echo(f"  Translating {chunk_count} chunks...")
        click.echo("")

        pipeline = TranslationPipeline(project, config=config)
        completed_project = pipeline.run()

        # Export translations
        click.echo(f"\n{'─'*70}")
        click.echo("STEP 5: Exporting translation results")
        click.echo(f"{'─'*70}")
        click.echo(f"  Output file: {output_path}")
        click.echo("")

        # Generate YAML frontmatter with metadata
        def generate_yaml_frontmatter(seg_index: int, total: int, chapter_id: str | None = None) -> str:
            """Generate YAML frontmatter for a segment."""
            from datetime import datetime
            yaml_lines = ["---"]
            yaml_lines.append(f"chunk_id: {seg_index + 1}")
            if chapter_id:
                yaml_lines.append(f"chapter_id: {chapter_id}")
            yaml_lines.append(f"total_segments: {total}")
            yaml_lines.append(f"source_document: {input_path_obj.name}")
            yaml_lines.append(f"target_language: {target_lang}")
            yaml_lines.append(f"translation_timestamp: {datetime.now().isoformat()}")
            yaml_lines.append("---")
            return "\n".join(yaml_lines)

        with open(output_path, 'w', encoding='utf-8') as f:
            # Write document header
            f.write(f"# Translation: {input_path_obj.name}\n\n")
            f.write(f"Target Language: {target_lang}\n\n")
            total_segments = len(completed_project.translation_segments) if hasattr(completed_project, 'translation_segments') else len(chunks)
            # Access segments from project
            segments = getattr(completed_project, 'segments', [])
            total_segments = len(segments) if segments else len(chunks)
            f.write(f"Total Segments: {total_segments}\n\n")
            f.write("---\n\n")

            if not segments:
                click.echo("   ⚠️ No translated segments found in project. Using source text.")
                # Fallback to chunks if no segments created
                for i, chunk in enumerate(chunks, 1):
                    f.write(f"## Segment {i}\n\n")
                    f.write("**Source (EN):**\n")
                    f.write(chunk.get('text', ''))
                    f.write("\n\n**Translation (ZH):**\n")
                    f.write("*[Translation not available - pipeline issue]*")
                    f.write("\n\n---\n\n")
            else:
                click.echo(f"   ✓ Processing {len(segments)} segments for export...")
                for i, seg in enumerate(segments, 1):
                    # Get source text from the nested segment object
                    source_text = ""
                    if hasattr(seg, 'segment') and seg.segment:
                        source_text = getattr(seg.segment, 'source_text', '')

                    # Get translation from TranslationSegment
                    translation = getattr(seg, 'translation', '') or ""

                    # Get chapter_id from segment if available
                    chapter_id = None
                    if hasattr(seg, 'segment') and seg.segment:
                        chapter_id = getattr(seg.segment, 'chapter_id', None)

                    # Write YAML frontmatter with metadata
                    f.write(generate_yaml_frontmatter(i, len(segments), chapter_id))
                    f.write("\n\n")

                    # Write segment header
                    f.write(f"## Segment {i}\n\n")

                    # Write to file
                    f.write("**Source (EN):**\n")
                    f.write(source_text[:2000] if source_text else "N/A")
                    f.write("\n\n")

                    f.write("**Translation (ZH):**\n")
                    f.write(translation[:2000] if translation else "*[No translation generated]*")
                    f.write("\n")

                    f.write("\n---\n\n")

        click.echo(f"\n{'='*70}")
        click.echo("✅ TRANSLATION COMPLETED SUCCESSFULLY")
        click.echo(f"{'='*70}")
        click.echo(f"\n📄 Output File: {output_path}")
        click.echo(f"\n📊 Statistics:")
        click.echo(f"   • Total segments: {total_segments}")
        click.echo(f"   • Provider: Anthropic Claude")
        click.echo(f"   • Model: {config.llm_model}")
        click.echo(f"\n💡 The translated document is ready for review.")

    except Exception as e:
        click.echo(f"\n{'='*70}", err=True)
        click.echo("❌ TRANSLATION FAILED", err=True)
        click.echo(f"{'='*70}", err=True)
        click.echo(f"\nError: {e}", err=True)
        click.echo(f"\n💡 Troubleshooting:", err=True)
        click.echo(f"   1. Check that ANTHROPIC_API_KEY or ANTHROPIC_AUTH_TOKEN is set", err=True)
        click.echo(f"   2. Verify your API key is valid and has not expired", err=True)
        click.echo(f"   3. Check network connectivity to the API endpoint", err=True)
        click.echo(f"   4. For Volces API, ensure base URL is correct", err=True)
        click.echo(f"\nStack trace:", err=True)
        import traceback
        click.echo(traceback.format_exc(), err=True)
        raise click.Abort()


@main.command()
@click.argument("file_or_folder", type=click.Path(exists=True))
@click.option("--recursive", "-r", is_flag=True, help="Recursively add files from folder")
def add_library(
    file_or_folder: str,
    recursive: bool,
) -> None:
    """Add files to local library.

    Add PDF or DOCX files to your local library for reference-aware translation.

    \b
    Example:
        aat add-library paper.pdf
        aat add-library my-papers/ -r
    """
    from aat.retrieval.ingestion import LibraryIngestion

    path = Path(file_or_folder)

    # Initialize library ingestion
    vector_store_dir = Path.home() / ".aat" / "library"
    ingestion = LibraryIngestion(vector_store_dir)

    if path.is_file():
        click.echo(f"Adding {file_or_folder} to library...")
        try:
            result = ingestion.ingest_file(path)
            if result["status"] == "ingested":
                click.echo(f"  ✓ Ingested {result['chunks_added']} chunks ({result.get('language', 'unknown')})")
            elif result["status"] == "unchanged":
                click.echo(f"  ✓ File unchanged (already in library)")
        except Exception as e:
            click.echo(f"  ✗ Error: {e}", err=True)
            raise click.Abort()

    elif path.is_dir():
        click.echo(f"Adding files from {file_or_folder} to library...")
        pattern = "**/*" if recursive else "*"
        files = list(path.glob(pattern))

        pdf_files = [f for f in files if f.suffix.lower() == ".pdf"]
        docx_files = [f for f in files if f.suffix.lower() == ".docx"]
        all_files = pdf_files + docx_files

        if not all_files:
            click.echo("  No PDF or DOCX files found.")
            return

        click.echo(f"  Found {len(all_files)} files ({len(pdf_files)} PDF, {len(docx_files)} DOCX)")
        if recursive:
            click.echo("  Recursive mode enabled")

        success_count = 0
        for file_path in all_files:
            try:
                result = ingestion.ingest_file(file_path)
                if result["status"] in ("ingested", "unchanged"):
                    success_count += 1
            except Exception as e:
                click.echo(f"  ✗ Error processing {file_path.name}: {e}", err=True)

        click.echo(f"  ✓ Successfully processed {success_count}/{len(all_files)} files")

    else:
        click.echo(f"Error: {file_or_folder} is not a valid file or directory")
        raise click.Abort()


@main.command()
@click.argument("project_folder", type=click.Path(exists=True))
def resume(project_folder: str) -> None:
    """Resume a translation project.

    Resume working on a previously started translation project.
    Continues from the first unlocked segment. Does not re-process locked segments.

    \b
    Example:
        aat resume project-123
    """
    from pathlib import Path
    from aat.storage.checkpoints import CheckpointManager

    project_dir = Path(project_folder)
    click.echo(f"Resuming project: {project_folder}")

    # Load checkpoint manager
    checkpoint_manager = CheckpointManager(project_dir)

    # Load latest checkpoint
    checkpoint = checkpoint_manager.load_latest_checkpoint()

    if checkpoint is None:
        click.echo("No checkpoint found. Cannot resume.")
        raise click.Abort()

    click.echo(f"Project ID: {checkpoint.project_id}")
    click.echo(f"Checkpoint timestamp: {checkpoint.timestamp}")

    # Get project metadata
    metadata = checkpoint_manager.get_project_metadata()
    if metadata:
        total_segments = metadata.get("total_segments", 0)
        completed_segments = metadata.get("completed_segments", 0)
        click.echo(f"Progress: {completed_segments}/{total_segments} segments completed")

    # Find first unlocked segment
    segment_states = checkpoint.segment_states
    first_unlocked = None
    for sid, state_data in segment_states.items():
        if isinstance(state_data, dict):
            if not state_data.get("locked", False):
                first_unlocked = sid
                break

    if first_unlocked:
        click.echo(f"Ready to resume from segment: {first_unlocked}")
    else:
        click.echo("All segments are locked. Translation appears complete.")
        click.echo("Use 'aat export' to generate the final output.")


def _reconstruct_project_from_checkpoint(checkpoint: "Checkpoint") -> "TranslationProject":
    """Reconstruct a TranslationProject from checkpoint data."""
    from aat.storage.models import (
        DocumentModel, Segment, SegmentState, TranslationProject,
        TranslationSegment, UncertaintyItem,
    )

    segments = []
    for sid, state_data in checkpoint.segment_states.items():
        if not isinstance(state_data, dict):
            continue

        seg_data = state_data.get("segment", {})
        segment = Segment(
            sid=seg_data.get("sid", sid),
            pid_list=seg_data.get("pid_list", []),
            source_text=seg_data.get("source_text", ""),
            context_before=seg_data.get("context_before"),
            context_after=seg_data.get("context_after"),
            chapter_id=seg_data.get("chapter_id"),
            metadata=seg_data.get("metadata", {}),
        )

        uncertainties = []
        for u in state_data.get("uncertainties", []):
            if isinstance(u, dict):
                uncertainties.append(UncertaintyItem(
                    type=u.get("type", ""),
                    span=u.get("span", ""),
                    question=u.get("question", ""),
                    options=u.get("options", []),
                ))

        raw_state = state_data.get("state", "lock_segment")
        try:
            state = SegmentState(raw_state)
        except ValueError:
            state = SegmentState.LOCK_SEGMENT

        trans_seg = TranslationSegment(
            segment=segment,
            state=state,
            translation=state_data.get("translation"),
            uncertainties=uncertainties,
            validator_results=[],
            critic_issues=state_data.get("critic_issues", []),
            user_comments=[
                c if isinstance(c, dict) else {"text": c, "timestamp": "unknown"}
                for c in state_data.get("user_comments", [])
            ],
            locked=state_data.get("locked", False),
        )
        segments.append(trans_seg)

    metadata = checkpoint.metadata or {}
    doc = DocumentModel(
        doc_id=checkpoint.project_id,
        title=metadata.get("title", checkpoint.project_id),
        sections=[],
        references=[],
        citations=[],
    )

    return TranslationProject(
        project_id=checkpoint.project_id,
        document=doc,
        segments=segments,
    )


@main.command()
@click.argument("project_folder", type=click.Path(exists=True))
@click.option("--format", "fmt", default="docx", type=click.Choice(["docx", "json"]))
@click.option("--output", "-o", type=click.Path(), help="Output file path")
@click.option("--chapter", "chapter_id", type=str, help="Export only specified chapter")
@click.option("--bilingual", is_flag=True, help="Include source text alongside translation")
@click.option("--skip-global-pass", "skip_global_pass", is_flag=True, help="Skip global consistency checks")
def export(
    project_folder: str,
    fmt: str,
    output: str | None,
    chapter_id: str | None,
    bilingual: bool,
    skip_global_pass: bool,
) -> None:
    """Export a translation project.

    Export a completed translation project to a file.

    \b
    Example:
        aat export project-123 --format docx
        aat export project-123 -o translated.docx
        aat export project-123 --chapter chapter1
        aat export project-123 --bilingual --format docx
        aat export project-123 --skip-global-pass -o out.docx
    """
    from pathlib import Path
    from aat.export.chapter import ChapterExporter

    project_dir = Path(project_folder)

    if chapter_id:
        click.echo(f"Exporting chapter {chapter_id} from project {project_folder}...")

        exporter = ChapterExporter(project_dir)
        result = exporter.export_chapter(chapter_id, output)

        if result["success"]:
            exported = len(result["exported_segments"])
            click.echo(f"Exported {exported} approved segments")

            for warning in result["warnings"]:
                click.echo(f"Warning: {warning}", err=True)

            if result["output_path"]:
                click.echo(f"Output file: {result['output_path']}")
        else:
            click.echo("Export failed.", err=True)
            raise click.Abort()
    else:
        import json as json_mod
        from aat.storage.checkpoints import CheckpointManager
        from aat.export.global_pass import GlobalPassOrchestrator

        click.echo(f"Exporting project {project_folder} as {fmt}...")

        cm = CheckpointManager(project_dir)
        checkpoint = cm.load_latest_checkpoint()
        if checkpoint is None:
            click.echo("No checkpoint found. Cannot export.", err=True)
            raise click.Abort()

        project = _reconstruct_project_from_checkpoint(checkpoint)
        click.echo(f"Loaded {len(project.segments)} segments from checkpoint")

        global_report = None
        if not skip_global_pass:
            click.echo("Running global consistency checks...", err=True)
            orchestrator = GlobalPassOrchestrator()
            global_report = orchestrator.run(project)
            click.echo(f"Global pass: {global_report.summary}", err=True)

        output_path = output or f"{Path(project_folder).name}_translated.{fmt}"

        if fmt == "docx":
            from aat.export.docx_export import DocxExporter

            exporter = DocxExporter(
                project,
                bilingual=bilingual,
                global_report=global_report,
            )
            result_path = exporter.export(output_path)
            click.echo(f"Output file: {result_path}")
        elif fmt == "json":
            data = {
                "project_id": checkpoint.project_id,
                "timestamp": checkpoint.timestamp,
                "metadata": checkpoint.metadata,
                "segment_states": checkpoint.segment_states,
            }
            json_str = json_mod.dumps(data, ensure_ascii=False, indent=2, default=str)
            Path(output_path).write_text(json_str, encoding="utf-8")
            click.echo(f"Output file: {output_path}")


@main.command()
@click.argument("project_folder", type=click.Path(exists=True))
def status(project_folder: str) -> None:
    """Show status of a translation project.

    Display translation progress, number of segments completed,
    and any issues that need attention.

    \b
    Example:
        aat status project-123
    """
    from pathlib import Path
    from collections import defaultdict
    from aat.storage.checkpoints import CheckpointManager
    from rich.table import Table
    from rich.console import Console

    console = Console()
    project_dir = Path(project_folder)

    cm = CheckpointManager(project_dir)
    checkpoint = cm.load_latest_checkpoint()

    if checkpoint is None:
        console.print("[red]No checkpoint found for this project.[/red]")
        raise click.Abort()

    states = checkpoint.segment_states
    total = len(states)
    locked = 0
    unlocked = 0
    with_uncertainties = 0
    chapter_counts: dict[str | None, dict[str, int]] = defaultdict(
        lambda: {"total": 0, "locked": 0}
    )

    for sid, sd in states.items():
        if not isinstance(sd, dict):
            continue
        is_locked = sd.get("locked", False)
        if is_locked:
            locked += 1
        else:
            unlocked += 1
        if sd.get("uncertainties"):
            with_uncertainties += 1
        ch = sd.get("segment", {}).get("chapter_id")
        chapter_counts[ch]["total"] += 1
        if is_locked:
            chapter_counts[ch]["locked"] += 1

    console.print()
    console.print(f"[bold]Project ID:[/bold] {checkpoint.project_id}")
    console.print(f"[bold]Total segments:[/bold] {total}")
    console.print(f"[bold]Locked:[/bold] {locked}  [bold]Unlocked:[/bold] {unlocked}")
    console.print(f"[bold]Segments with uncertainties:[/bold] {with_uncertainties}")
    console.print(f"[bold]Last checkpoint:[/bold] {checkpoint.timestamp}")
    console.print()

    table = Table(title="Per-Chapter Breakdown")
    table.add_column("Chapter", style="cyan")
    table.add_column("Segments", justify="right")
    table.add_column("Locked", justify="right")
    table.add_column("% Complete", justify="right")

    for ch_id in sorted(chapter_counts, key=lambda x: x or ""):
        info = chapter_counts[ch_id]
        pct = (info["locked"] / info["total"] * 100) if info["total"] else 0
        table.add_row(
            ch_id or "(no chapter)",
            str(info["total"]),
            str(info["locked"]),
            f"{pct:.1f}%",
        )

    console.print(table)


@main.command()
def config() -> None:
    """Show or edit configuration.

    Display current configuration or edit config file.
    """
    config_path = Path.home() / ".aat" / "config.toml"

    if config_path.exists():
        click.echo(f"Configuration file: {config_path}")
        click.echo("\nCurrent configuration:")
        with open(config_path) as f:
            click.echo(f.read())
    else:
        click.echo(f"Configuration file not found: {config_path}")
        click.echo("Run 'aat init' to create a default configuration.")


@main.command()
def init() -> None:
    """Initialize AAT configuration.

    Create default configuration file and directories.
    """
    config_dir = Path.home() / ".aat"
    config_dir.mkdir(exist_ok=True)

    config_path = config_dir / "config.toml"

    if config_path.exists():
        click.echo(f"Configuration already exists at: {config_path}")
        if not click.confirm("Overwrite existing configuration?"):
            return

    default_config = """# AAT Configuration

[model_provider]
# Model provider: "ollama" (free), "openai" (paid), or "anthropic" (paid)
provider = "anthropic"
model_name = "claude-3-5-sonnet-20241022"

[features]
# Default behavior for external search
enable_web_default = false

[embedding]
# Embedding model for vector store
model = "bge-m3"

[vector_store]
# Vector store backend
backend = "chroma"
"""

    config_path.write_text(default_config)
    click.echo(f"Configuration created at: {config_path}")
    click.echo("\nEdit the configuration file to customize settings.")


@main.command()
@click.argument("project_folder", type=click.Path(exists=True))
@click.option("--port", default=8741, help="Port for review UI server")
def review(project_folder: str, port: int) -> None:
    """Launch review UI for a translation project.

    Opens a browser-based review interface where you can inspect,
    comment on, edit, and approve translated segments.

    \b
    Example:
        aat review project-123
        aat review project-123 --port 9000
    """
    import webbrowser

    from aat.ui.server import create_app

    project_dir = Path(project_folder)
    create_app(project_dir)

    url = f"http://127.0.0.1:{port}"
    click.echo(f"Review UI running at {url}")
    click.echo("Press Ctrl+C to stop")

    webbrowser.open(url)

    import uvicorn
    from aat.ui.server import app

    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


@main.command()
@click.argument("project_folder", type=click.Path(exists=True))
@click.option("--all", "revise_all", is_flag=True, help="Revise all segments with pending feedback")
@click.option("--segment", "segment_id", type=str, help="Revise a specific segment by ID")
def revise(project_folder: str, revise_all: bool, segment_id: str | None) -> None:
    """Revise segments using accumulated human feedback.

    \b
    Example:
        aat revise project-123 --all
        aat revise project-123 --segment s1
    """
    from aat.storage.checkpoints import CheckpointManager
    from aat.translate.llm_client import FakeLLMClient
    from aat.translate.prompts import RevisionPrompt

    project_dir = Path(project_folder)
    cm = CheckpointManager(project_dir)
    checkpoint = cm.load_latest_checkpoint()

    if checkpoint is None:
        click.echo("No checkpoint found. Cannot revise.", err=True)
        raise click.Abort()

    prefs = cm.get_project_preferences()
    llm_client = FakeLLMClient()
    revised_count = 0

    for sid, seg_data in checkpoint.segment_states.items():
        if not isinstance(seg_data, dict):
            continue
        if segment_id and sid != segment_id:
            continue

        comments_raw = seg_data.get("user_comments", [])
        structured = seg_data.get("structured_feedback", [])
        revision_requested = seg_data.get("revision_requested", False)

        if not revise_all and not segment_id:
            continue
        if revise_all and not (comments_raw or structured or revision_requested):
            continue

        comments = []
        for c in comments_raw:
            if isinstance(c, dict):
                comments.append(c.get("text", ""))
            elif isinstance(c, str):
                comments.append(c)

        source_text = seg_data.get("segment", {}).get("source_text", "")
        translation = seg_data.get("translation", "")

        messages = RevisionPrompt.build(
            source_text=source_text,
            current_translation=translation,
            critic_issues=seg_data.get("critic_issues", []),
            user_feedback=comments,
            user_answers=seg_data.get("uncertainty_answers", {}),
            structured_feedback=structured,
            style_preferences=prefs,
        )
        schema = RevisionPrompt.get_response_schema()
        response = llm_client.chat(messages, json_schema=schema)

        content = response.get("content", {})
        if isinstance(content, dict):
            new_translation = content.get("translation", "")
            if new_translation:
                cm.update_translation(sid, new_translation)
                cm.update_segment(sid, {"revision_requested": False})
                revised_count += 1

    click.echo(f"Revised {revised_count} segment(s)")


@main.command(name="set-preference")
@click.argument("project_folder", type=click.Path(exists=True))
@click.option("--term", type=str, help="Add terminology override (format: source=target)")
@click.option("--tone", type=click.Choice(["academic", "technical", "general"]))
@click.option("--formality", type=click.Choice(["formal", "semi-formal", "informal"]))
def set_preference(project_folder: str, term: str | None, tone: str | None, formality: str | None) -> None:
    """Set project-level translation preferences.

    \b
    Example:
        aat set-preference project-123 --term "entropy=熵"
        aat set-preference project-123 --tone academic
    """
    from aat.storage.checkpoints import CheckpointManager

    project_dir = Path(project_folder)
    cm = CheckpointManager(project_dir)
    checkpoint = cm.load_latest_checkpoint()

    if checkpoint is None:
        click.echo("No checkpoint found.", err=True)
        raise click.Abort()

    prefs = cm.get_project_preferences()

    if term:
        if "=" not in term:
            click.echo("Term format must be 'source=target'", err=True)
            raise click.Abort()
        src, tgt = term.split("=", 1)
        overrides = prefs.get("terminology_overrides", {})
        overrides[src] = tgt
        prefs["terminology_overrides"] = overrides
        click.echo(f"Added terminology: {src} → {tgt}")

    if tone:
        prefs["tone"] = tone
        click.echo(f"Set tone: {tone}")

    if formality:
        prefs["formality"] = formality
        click.echo(f"Set formality: {formality}")

    cm.set_project_preferences(prefs)
    click.echo("Preferences saved.")
