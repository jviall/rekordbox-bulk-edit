"""Convert command for rekordbox-bulk-edit."""

import os
import sys
from pathlib import Path

import click
import ffmpeg
from pyrekordbox import Rekordbox6Database

from rekordbox_bulk_edit.utils import get_audio_info, print_track_info


def convert_flac_to_aiff(flac_path, aiff_path):
    """Convert FLAC file to AIFF using ffmpeg, preserving bit depth"""
    try:
        # Get original audio info
        audio_info = get_audio_info(flac_path)
        bit_depth = audio_info["bit_depth"]

        # Map bit depth to appropriate PCM codec
        codec_map = {16: "pcm_s16be", 24: "pcm_s24be", 32: "pcm_s32be"}

        codec = codec_map.get(bit_depth, "pcm_s16be")  # Default to 16-bit if unknown

        click.echo(f"  Converting with {bit_depth}-bit depth using codec: {codec}")

        (
            ffmpeg.input(flac_path)
            .output(aiff_path, acodec=codec)
            .overwrite_output()
            .run(capture_stdout=True, capture_stderr=True)
        )
        return True
    except ffmpeg.Error as e:
        click.echo(f"FFmpeg error converting {flac_path}: {e}")
        if e.stderr:
            click.echo(f"FFmpeg stderr output:\n{e.stderr.decode()}")
        return False
    except Exception as e:
        click.echo(f"Error converting {flac_path}: {e}")
        return False


def update_database_record(db, content_id, new_filename, new_folder):
    """Update database record with new AIFF file information"""
    try:
        # Get the content record
        content = db.get_content().filter_by(ID=content_id).first()
        if not content:
            raise Exception(f"Content record with ID {content_id} not found")

        # Get audio info of converted AIFF file
        aiff_full_path = os.path.join(new_folder, new_filename)
        converted_audio_info = get_audio_info(aiff_full_path)
        converted_bit_depth = converted_audio_info["bit_depth"]
        converted_bitrate = converted_audio_info["bitrate"]

        # Compare with bit depth stored in database
        # Try common field names for bit depth
        database_bit_depth = None
        if hasattr(content, "BitDepth"):
            database_bit_depth = getattr(content, "BitDepth")

        if database_bit_depth and converted_bit_depth != database_bit_depth:
            raise Exception(
                f"Bit depth mismatch: database shows {database_bit_depth}-bit, converted file is {converted_bit_depth}-bit"
            )

        if database_bit_depth:
            click.echo(
                f"  ✓ Bit depth verification passed: {converted_bit_depth}-bit matches database"
            )
        else:
            click.echo(
                f"  ⚠ Warning: Could not verify bit depth - no bit depth field found in database"
            )

        # Update relevant fields
        content.FileNameL = new_filename
        content.FolderPath = aiff_full_path
        content.FileType = 12  # AIFF file type
        content.BitRate = (
            converted_bitrate  # Update bitrate to reflect AIFF's constant bitrate
        )

        click.echo(f"  ✓ Updated BitRate from {content.BitRate or 0} to {converted_bitrate}")

        # Note: No commit here - will be done centrally
        return True

    except Exception as e:
        click.echo(f"Error updating database record {content_id}: {e}")
        raise  # Re-raise to be handled by caller


class UserQuit(Exception):
    """Exception raised when user chooses to quit"""
    pass


def confirm(question, default_yes=True):
    """Ask a yes/no question with default, or Q to quit"""
    default_prompt = "[Y/n/q]" if default_yes else "[y/N/q]"
    while True:
        response = click.prompt(f"{question} {default_prompt}", default="", show_default=False).strip().lower()
        if not response:
            return default_yes
        if response in ["y", "yes"]:
            return True
        if response in ["n", "no"]:
            return False
        if response in ["q", "quit"]:
            raise UserQuit("User chose to quit")
        click.echo("Please enter 'y', 'n', or 'q' to quit")


@click.command()
@click.option(
    "--dry-run", is_flag=True, help="Show what would be converted without actually doing it"
)
@click.option(
    "--auto-confirm", is_flag=True, help="Skip confirmation prompts (use with caution)"
)
def convert_command(dry_run, auto_confirm):
    """Convert FLAC files to AIFF format and update RekordBox database."""
    try:
        click.echo("FLAC to AIFF Converter")
        click.echo("=" * 21)
        click.echo()

        if dry_run:
            click.echo("DRY RUN MODE - No files will be converted or modified")
            click.echo()

        # Connect to RekordBox database
        click.echo("Connecting to RekordBox database...")
        db = Rekordbox6Database()

        # Check if we have a valid session early on
        if not db.session:
            click.echo("ERROR: No database session available")
            click.echo("ABORTING: Cannot continue without database access")
            sys.exit(1)

        # Get all FLAC files
        click.echo("Finding FLAC files...")
        all_content = db.get_content()
        flac_files = [content for content in all_content if content.FileType == 5]

        click.echo(f"Found {len(flac_files)} FLAC files to convert")

        if not flac_files:
            click.echo("No FLAC files found. Exiting.")
            return

        if dry_run:
            click.echo("\nFiles that would be converted:")
            print_track_info(flac_files)
            return

        # Process each file
        converted_files = []  # Track converted files for potential deletion

        for i, content in enumerate(flac_files, 1):
            flac_file_name = content.FileNameL or ""
            flac_full_path = content.FolderPath or ""
            flac_folder = os.path.dirname(flac_full_path)

            click.echo(f"\nProcessing {i}/{len(flac_files)}")

            # Show detailed track information
            print_track_info([content])
            click.echo()

            # Check if FLAC file exists
            if not os.path.exists(flac_full_path):
                click.echo(f"ERROR: FLAC file not found: {flac_full_path}")
                click.echo("ABORTING: Cannot continue with missing files")
                db.session.rollback()
                sys.exit(1)

            # Generate AIFF filename and path
            flac_path_obj = Path(flac_file_name)
            aiff_filename = flac_path_obj.stem + ".aiff"
            aiff_full_path = os.path.join(flac_folder, aiff_filename)

            # Check if AIFF already exists
            if os.path.exists(aiff_full_path):
                click.echo(f"WARNING: AIFF file already exists: {aiff_full_path}")
                click.echo("ABORTING: Cannot overwrite existing files")
                db.session.rollback()
                sys.exit(1)

            # Ask for confirmation
            try:
                if not auto_confirm and not confirm(
                    f"Convert track {flac_file_name} to AIFF?", default_yes=True
                ):
                    click.echo("Skipping this file...")
                    continue
            except UserQuit:
                if converted_files:
                    click.echo("User quit. You have uncommitted database changes.")
                    try:
                        if confirm("Commit database changes before quitting?", default_yes=True):
                            try:
                                db.session.commit()
                                click.echo("✓ Database changes committed successfully")
                                
                                # Ask about deleting FLAC files
                                try:
                                    if confirm("Delete original FLAC files?", default_yes=False):
                                        deleted_count = 0
                                        for file_info in converted_files:
                                            try:
                                                os.remove(file_info["flac_path"])
                                                deleted_count += 1
                                                click.echo(f"✓ Deleted {file_info['flac_path']}")
                                            except Exception as e:
                                                click.echo(f"⚠ Failed to delete {file_info['flac_path']}: {e}")
                                        click.echo(f"Deleted {deleted_count} of {len(converted_files)} FLAC files")
                                    else:
                                        click.echo("Original FLAC files preserved")
                                except UserQuit:
                                    click.echo("User quit. Original FLAC files preserved.")
                                    
                            except Exception as e:
                                click.echo(f"FATAL ERROR: Failed to commit database changes: {e}")
                                db.session.rollback()
                                sys.exit(1)
                        else:
                            click.echo("Rolling back database changes and cleaning up...")
                            db.session.rollback()
                            # Clean up converted AIFF files
                            for file_info in converted_files:
                                try:
                                    os.remove(file_info["aiff_path"])
                                    click.echo(f"✓ Cleaned up {file_info['aiff_path']}")
                                except:
                                    pass
                    except UserQuit:
                        click.echo("User quit. Rolling back database changes and cleaning up...")
                        db.session.rollback()
                        # Clean up converted AIFF files
                        for file_info in converted_files:
                            try:
                                os.remove(file_info["aiff_path"])
                                click.echo(f"✓ Cleaned up {file_info['aiff_path']}")
                            except:
                                pass
                else:
                    click.echo("User quit. No changes to commit.")
                sys.exit(0)

            # Convert file
            click.echo(f"Converting...")
            if not convert_flac_to_aiff(flac_full_path, aiff_full_path):
                click.echo("ABORTING: Conversion failed")
                db.session.rollback()
                # Clean up any converted files
                for converted_file in converted_files:
                    try:
                        os.remove(converted_file["aiff_path"])
                    except:
                        pass
                sys.exit(1)

            # Verify conversion was successful
            if not os.path.exists(aiff_full_path):
                click.echo("ABORTING: Converted file not found after conversion")
                db.session.rollback()
                sys.exit(1)

            # Update database (but don't commit yet)
            click.echo("Updating database record...")
            try:
                update_database_record(db, content.ID, aiff_filename, flac_folder)
                converted_files.append(
                    {
                        "flac_path": flac_full_path,
                        "aiff_path": aiff_full_path,
                        "content_id": content.ID,
                    }
                )
                click.echo(f"✓ Successfully converted and updated database record")
            except Exception as e:
                click.echo(f"ABORTING: Database update failed: {e}")
                db.session.rollback()
                # Clean up converted files
                try:
                    os.remove(aiff_full_path)
                    click.echo("Cleaned up converted file")
                except:
                    click.echo("Failed to clean up converted file")
                sys.exit(1)

        # Handle final commit and cleanup
        if converted_files:
            click.echo(
                f"\n🎉 Successfully converted {len(converted_files)} FLAC files to AIFF format"
            )

            try:
                if auto_confirm or confirm("Commit database changes?", default_yes=True):
                    try:
                        db.session.commit()
                        click.echo("✓ Database changes committed successfully")

                        # Ask about deleting FLAC files
                        try:
                            if auto_confirm or confirm(
                                "Delete original FLAC files?", default_yes=False
                            ):
                                deleted_count = 0
                                for file_info in converted_files:
                                    try:
                                        os.remove(file_info["flac_path"])
                                        deleted_count += 1
                                        click.echo(f"✓ Deleted {file_info['flac_path']}")
                                    except Exception as e:
                                        click.echo(
                                            f"⚠ Failed to delete {file_info['flac_path']}: {e}"
                                        )
                                click.echo(
                                    f"Deleted {deleted_count} of {len(converted_files)} FLAC files"
                                )
                            else:
                                click.echo("Original FLAC files preserved")
                        except UserQuit:
                            click.echo("User quit. Original FLAC files preserved.")
                            sys.exit(0)

                    except Exception as e:
                        click.echo(f"FATAL ERROR: Failed to commit database changes: {e}")
                        db.session.rollback()
                        sys.exit(1)
                else:
                    click.echo("Database changes rolled back")
                    db.session.rollback()
                    # Clean up converted AIFF files
                    for file_info in converted_files:
                        try:
                            os.remove(file_info["aiff_path"])
                            click.echo(f"✓ Cleaned up {file_info['aiff_path']}")
                        except:
                            click.echo(f"⚠ Failed to clean up {file_info['aiff_path']}")
            except UserQuit:
                click.echo("User quit. Rolling back database changes and cleaning up...")
                db.session.rollback()
                # Clean up converted AIFF files
                for file_info in converted_files:
                    try:
                        os.remove(file_info["aiff_path"])
                        click.echo(f"✓ Cleaned up {file_info['aiff_path']}")
                    except:
                        pass
                sys.exit(0)
        else:
            click.echo("No files were converted.")

    except Exception as e:
        click.echo(f"FATAL ERROR: {e}")
        try:
            if db.session:
                db.session.rollback()
        except:
            pass
        sys.exit(1)
