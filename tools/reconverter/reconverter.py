import adsk.core
import adsk.fusion
import traceback
import json
import os
import sys
import time
from pathlib import Path
import importlib


# Add the common folder to sys.path
COMMON_DIR = os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", "common"))
if COMMON_DIR not in sys.path:
    sys.path.append(COMMON_DIR)

import exporter
importlib.reload(exporter)
import view_control
from logger import Logger
import sketch_extrude_importer
importlib.reload(sketch_extrude_importer)
from sketch_extrude_importer import SketchExtrudeImporter


# Event handlers
handlers = []

class OnlineStatusChangedHandler(adsk.core.ApplicationEventHandler):
    def __init__(self):
        super().__init__()

    def notify(self, args):
        # Start when onlineStatusChanged handler returns
        start()


class Reconverter():
    """Reconstruction Converter
        Takes a reconstruction json file and converts it
        to different formats"""

    def __init__(self, json_file, output_dir):
        self.json_file = json_file
        self.output_dir = output_dir
        # References to the Fusion design
        self.app = adsk.core.Application.get()
        self.design = adsk.fusion.Design.cast(self.app.activeProduct)

    def reconstruct(self):
        """Reconstruct the design from the json file"""
        self.importer = SketchExtrudeImporter(self.json_file)
        self.importer.reconstruct(self.inc_export)

    def inc_export(self, data):
        """Callback function called whenever a the design changes
            i.e. when a curve is added or an extrude
            This enables us to save out incremental data"""
        if "extrude" in data:
            self.inc_export_extrude(data)

    def inc_export_extrude(self, data):
        """Save out incremental extrude data as reconstruction takes place"""
        extrude = data["extrude"]
        extrude_index = data["extrude_index"]
        extrude_data = data["extrude_data"]
        extrude_uuid = data["extrude_id"]
        sketch_profiles = data["sketch_profiles"]

        # Second extrude
        # Create a new body this time
        extrude_data["operation"] = "NewBodyFeatureOperation"
        extrude = self.importer.reconstruct_extrude_feature(
            extrude_data,
            extrude_uuid,
            extrude_index,
            sketch_profiles,
            second_extrude=True
        )

        smt_file = f"{self.json_file.stem}_{extrude_index:04}e.smt"
        obj_file = f"{self.json_file.stem}_{extrude_index:04}e.obj"
        smt_file_path = self.output_dir / smt_file
        obj_file_path = self.output_dir / obj_file
        bodies = []
        for body in extrude.bodies:
            bodies.append(body)
        exporter.export_smt_from_bodies(smt_file_path, bodies)
        assert smt_file_path.exists()
        exporter.export_obj_from_bodies(obj_file_path, bodies)
        assert obj_file_path.exists()

        # Rollback the timeline to before the last extrude
        extrude.timelineObject.rollTo(True)
        # Delete everything after that
        self.design.timeline.deleteAllAfterMarker()


def save_results(results_file, results):
    """Save out the results of conversion"""
    with open(results_file, "w", encoding="utf8") as f:
        json.dump(results, f, indent=4)


def load_results(results_file):
    """Load the results of conversion"""
    if results_file.exists():
        with open(results_file, "r", encoding="utf8") as f:
            return json.load(f)
    return {}


def start():
    app = adsk.core.Application.get()
    # Logger to print to the text commands window in Fusion
    logger = Logger()
    # Fusion requires an absolute path
    # current_dir = Path(__file__).resolve().parent
    data_dir = Path("E:/Autodesk/FusionGallery/Data/Reconstruction/d7/d7")
    output_dir = Path("E:/Autodesk/FusionGallery/Data/Reconstruction/d7/ExtrudeTools")
    if not output_dir.exists():
        output_dir.mkdir(parents=True)

    results_file = output_dir / "reconverter_results.json"
    results = load_results(results_file)

    # Get all the files in the data folder
    json_files = [f for f in data_dir.glob("*_[0-9][0-9][0-9][0-9].json")]
    # json_files = [
    #     # data_dir / "Couch.json",
    #     data_dir / "Hexagon.json"
    # ]

    json_count = len(json_files)
    success_count = 0
    for i, json_file in enumerate(json_files, start=1):
        if json_file.name in results:
            logger.log(f"[{i}/{json_count}] Skipping {json_file}")
        else:
            try:
                logger.log(f"[{i}/{json_count}] Processing {json_file}")
                # Immediately log this in case we crash
                results[json_file.name] = {}
                save_results(results_file, results)

                reconverter = Reconverter(json_file, output_dir)
                reconverter.reconstruct()
                success_count += 1
                results[json_file.name] = {
                    "status": "Success"
                }
            except Exception as ex:
                logger.log(f"Error exporting: {ex}")
                trace = traceback.format_exc()
                results[json_file.name] = {
                    "status": "Exception",
                    "exception": ex.__class__.__name__,
                    "exception_args": " ".join(ex.args),
                    "trace": trace
                }
            finally:
                # Close the document
                # Fusion automatically opens a new window
                # after the last one is closed
                app.activeDocument.close(False)
                save_results(results_file, results)
    logger.log("----------------------------")
    logger.log(f"[{success_count}/{json_count}] designs processed successfully")


def run(context):
    try:
        app = adsk.core.Application.get()
        # If we have started manually
        # we go ahead and startup
        if app.isStartupComplete:
            start()
        else:
            # If we are being started on startup
            # then we subscribe to ‘onlineStatusChanged’ event
            # This event is triggered on Fusion startup
            print("Setting up online status changed handler...")
            on_online_status_changed = OnlineStatusChangedHandler()
            app.onlineStatusChanged.add(on_online_status_changed)
            handlers.append(on_online_status_changed)

    except:
        print(traceback.format_exc())
