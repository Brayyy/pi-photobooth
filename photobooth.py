#!/usr/bin/env python3
# apt-get install -y python python-setuptools python-pip python-dev python-imaging imagemagick
# pip install picamera

import datetime
import os
import glob
import random
import math
from time import sleep
# import gc
import pydebug
from PIL import Image
import RPi.GPIO as GPIO
import picamera
import time

debug = pydebug.debug("photobooth")

TESTMODE_AUTOPRESS_BUTTON = False
TESTMODE_FAST = False
PIN_CAMERA_BTN = 18
PIN_EXIT_BTN = 24
TOTAL_PICS = 4
PREP_DELAY = 3
COUNTDOWN_FROM = 3
JPEG_QUALITY = 90
FINAL_REVIEW_DELAY = 5
RENDER_COMPOSITE = False
# aspect 4:3 (camera max/2) (minor move on capture)
PHOTO_W, PHOTO_H = 1296, 972
# aspect 4:3 (camera max) (no move on capture) (tends to crash)
# PHOTO_W, PHOTO_H = 2592, 1944

if TESTMODE_FAST:
    # TOTAL_PICS = 2     # number of pics to be taken
    PREP_DELAY = 0     # number of seconds at step 1 as users prep to have photo taken
    COUNTDOWN_FROM = 0
    FINAL_REVIEW_DELAY = 1

GPIO.setmode(GPIO.BCM)
GPIO.setup(PIN_CAMERA_BTN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(PIN_EXIT_BTN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
CAMERA = picamera.PiCamera()
#CAMERA.rotation = 270
CAMERA.annotate_text_size = 150
CAMERA.resolution = (PHOTO_W, PHOTO_H)
# When preparing for photos, the preview will be flipped horizontally.
CAMERA.hflip = True
CAMERA.framerate = 15
CAMERA.awb_mode = "flash"
# CAMERA.brightness = 52
# CAMERA.contrast = -5

REAL_PATH = os.path.dirname(os.path.realpath(__file__))

def print_overlay(string_to_print):
    # debug("print_overlay(%s)" % string_to_print)
    CAMERA.annotate_text = string_to_print

def flash(on):
    GPIO.setup(PIN_FLASH, GPIO.IN if on is True else GPIO.OUT)

def get_base_filename_for_images():
    debug("get_base_filename_for_images()")
    filename = "/snaps/%s" % str(datetime.datetime.now()).split(".")[0]
    filename = filename.replace(" ", "_").replace(":", "").replace("-", "")
    return filename

def remove_overlay(overlay_id):
    debug("remove_overlay(%s)" % id(overlay_id))
    if overlay_id != -1:
        CAMERA.remove_overlay(overlay_id)

def overlay_image(image_path, duration=0, layer=3):
    # The camera block size is 32x16 so any image data provided to a renderer
    # must have a width with a multiple of 32, and a height with a multiple of 16
    # http://picamera.readthedocs.io/en/release-1.10/recipes1.html#overlaying-images-on-the-preview
    debug("overlay_image(%s, %s, %s)" % (image_path, duration, layer))
    # Load the arbitrarily sized image
    img = Image.open(REAL_PATH + image_path)
    # Create an image padded to the required size with, mode 'RGB'
    pad = Image.new("RGB", (
        ((img.size[0] + 31) // 32) * 32,
        ((img.size[1] + 15) // 16) * 16,
    ))
    # Paste the original image into the padded one
    pad.paste(img, (0, 0))
    # Get the padded image data
    padded_img_data = pad.tobytes()
    # Add the overlay with the padded image as the source, with original image dimensions
    o_id = CAMERA.add_overlay(padded_img_data, size=img.size)
    o_id.layer = layer
    # Return overlay id, or wait, remove then return -1
    # Use remove_overlay(o_id) to manually clear overlay
    if duration == 0:
        return o_id
    sleep(duration)
    CAMERA.remove_overlay(o_id)
    return -1

def timed_overlay(overlay_key, filename_prefix=""):
    debug("timed_overlay(%s)" % overlay_key)
    overlay_cfg = {
        "pose1": (PREP_DELAY, "/assets/get_ready_1.jpg"),
        "pose2": (PREP_DELAY, "/assets/get_ready_2.jpg"),
        "pose3": (PREP_DELAY, "/assets/get_ready_3.jpg"),
        "pose4": (PREP_DELAY, "/assets/get_ready_4.jpg"),
        "processing": (2, "/assets/processing.jpg"),
        "done": (FINAL_REVIEW_DELAY, "/assets/all_done.jpg"),
        "2x2": (FINAL_REVIEW_DELAY, "%s_2x2.jpg" % filename_prefix),
    }
    seconds = overlay_cfg[overlay_key][0]
    image = overlay_cfg[overlay_key][1]
    overlay_image(image, seconds)

def take_photo(photo_number, filename_prefix):
    debug("take_photo(%s, ...)" % (photo_number))
    filename = "%s_p%s.jpg" % (filename_prefix, photo_number)
    # countdown from X, and display countdown on screen
    for counter in range(COUNTDOWN_FROM, 0, -1):
        # push the number down to bottom of display
        print_overlay("\n\n\n\n%s" % counter)
        debug("take_photo(%s, waiting ...%s)" % (photo_number, counter))
        sleep(1)
    # flash(True)
    # time.sleep(.25)
    CAMERA.annotate_text = ''
    CAMERA.capture(REAL_PATH + filename)
    # flash(False)
    debug("take_photo(%s, ...) Saved %s" % (photo_number, filename))

def playback_singles(filename_prefix):
    debug("playback_singles(%s)" % filename_prefix)
    prev_overlay = False
    for photo_number in range(1, TOTAL_PICS + 1):
        filename = "%s_p%s.jpg" % (filename_prefix, photo_number)
        this_overlay = overlay_image(filename, False, 3+TOTAL_PICS)
        # Only remove the previous overlay after a new overlay is added.
        if prev_overlay:
            remove_overlay(prev_overlay)
        sleep(2)
        prev_overlay = this_overlay
    remove_overlay(prev_overlay)

def assemble_2x2(filename_prefix):
    """Assembles four pictures into a 2x2 grid

    It assumes, all original pictures have the same aspect ratio as
    the resulting image.

    For the thumbnail sizes we have:
    h = (H - 2 * a - 2 * b) / 2
    w = (W - 2 * a - 2 * b) / 2

                                W
            |---------------------------------------|

       ---  +---+-------------+---+-------------+---+  ---
        |   |                                       |   |  a
        |   |   +-------------+   +-------------+   |  ---
        |   |   |             |   |             |   |   |
        |   |   |      0      |   |      1      |   |   |  h
        |   |   |             |   |             |   |   |
        |   |   +-------------+   +-------------+   |  ---
      H |   |                                       |   |  2*b
        |   |   +-------------+   +-------------+   |  ---
        |   |   |             |   |             |   |   |
        |   |   |      2      |   |      3      |   |   |  h
        |   |   |             |   |             |   |   |
        |   |   +-------------+   +-------------+   |  ---
        |   |                                       |   |  a
       ---  +---+-------------+---+-------------+---+  ---

            |---|-------------|---|-------------|---|
              a        w       2*b       w        a
    """
    f = "assemble_2x2(%s)" % filename_prefix
    s = time.time()
    debug(f)

    input_filenames = []
    for i in range (1, TOTAL_PICS + 1):
        input_filenames.append("%s_p%s.jpg" % (filename_prefix, i))

    # Thumbnail size of pictures
    outer_border = math.floor(PHOTO_W / 50)
    inner_border = math.floor(PHOTO_W / 72)
    thumb_box = (int(PHOTO_W / 2), int(PHOTO_H / 2))
    thumb_size = (
        int(thumb_box[0] - outer_border - inner_border),
        int(thumb_box[1] - outer_border - inner_border)
    )
    debug("%s Got vars" % f)

    bg_glob = "%s/assets/2x2_at_%sx%s*" % (REAL_PATH, PHOTO_W, PHOTO_H);
    bg_list = glob.glob(bg_glob)
    bg_url = random.choice(bg_list)

    # If template asset is found, use that for background.
    # Else, create output image with white background
    if os.path.isfile(bg_url):
        output_image = Image.open(bg_url)
        debug("%s Opened image %sx%s %s" % (f, PHOTO_W, PHOTO_H, bg_url))
    else:
        output_image = Image.new('RGB', (PHOTO_W, PHOTO_H), (255, 255, 255))
        debug("%s Created new image %sx%s" % (f, PHOTO_W, PHOTO_H))

    for photo_number in range(0, TOTAL_PICS):
        img = Image.open(REAL_PATH + input_filenames[photo_number])#.transpose(Image.FLIP_LEFT_RIGHT)
        debug("%s Loaded #%s" % (f, photo_number))
        img.thumbnail(thumb_size)
        offsets = {
            1: (int(thumb_box[0] - inner_border - img.size[0]),
                int(thumb_box[1] - inner_border - img.size[1])),
            0: (int(thumb_box[0] + inner_border),
                int(thumb_box[1] - inner_border - img.size[1])),
            3: (int(thumb_box[0] - inner_border - img.size[0]),
                int(thumb_box[1] + inner_border)),
            2: (int(thumb_box[0] + inner_border),
                int(thumb_box[1] + inner_border)),
        }
        output_image.paste(img, offsets[photo_number])
        debug("%s Pasted #%s" % (f, photo_number))

    # Save assembled image
    output_filename = "%s_2x2.jpg" % filename_prefix
    # output_image.save(REAL_PATH + output_filename, "JPEG")
    output_image.transpose(Image.FLIP_LEFT_RIGHT).save(REAL_PATH + output_filename, "JPEG", quality=JPEG_QUALITY)
    # overlay_image(output_filename, 3, 4)
    # return output_filename
    debug("%s took: %2.3fs" % (f, time.time() - s))

def intro_loop():
    debug("intro_loop()")
    i = 0
    blink_speed = 5
    ol_intro1 = overlay_image("/assets/intro_1.png", 0, 3)
    ol_intro2 = overlay_image("/assets/intro_2.png", 0, 4)
    while True:
        i += 1
        if i == blink_speed:
            ol_intro2.alpha = 255
        elif i == (2 * blink_speed):
            ol_intro2.alpha = 0
            i = 0
        pressed_snap = GPIO.wait_for_edge(PIN_CAMERA_BTN, GPIO.FALLING, timeout=200)
        if TESTMODE_AUTOPRESS_BUTTON:
            pressed_snap = True
        if pressed_snap:
            break
        # pressed_exit = GPIO.wait_for_edge(PIN_EXIT_BTN, GPIO.FALLING, timeout=100)
    debug("show_intro() Snap pressed!")
    remove_overlay(ol_intro2)
    remove_overlay(ol_intro1)

def main():
    overlay_image("/assets/black.jpg", 0, 0)
    CAMERA.start_preview()
    while True:
        intro_loop()
        filename_prefix = get_base_filename_for_images()
        for photo_number in range(1, TOTAL_PICS + 1):
            timed_overlay("pose%s" % photo_number)
            take_photo(photo_number, filename_prefix)
        # Show processing message prior to showing previews, it will block the camera
        ol_black = overlay_image("/assets/black.jpg", 0, 3)
        ol_proc = overlay_image("/assets/processing.jpg", 0, 4)
        if RENDER_COMPOSITE:
            assemble_2x2(filename_prefix)
            remove_overlay(ol_proc)
            timed_overlay("2x2", filename_prefix)
        else:
            sleep(2)
            remove_overlay(ol_proc)
            playback_singles(filename_prefix)
        timed_overlay("done")
        remove_overlay(ol_black)
        # If we were doing a test run, exit here.
        if TESTMODE_AUTOPRESS_BUTTON:
            break

if __name__ == "__main__":
    start = time.time()
    try:
        main()
    except KeyboardInterrupt:
        print("goodbye")
    except Exception as exception:
        print("unexpected error: %s" % exception)
    finally:
        CAMERA.stop_preview()
        CAMERA.close()
        GPIO.cleanup()

    print("Total run time: %2.3f" % (time.time() - start))
