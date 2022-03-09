#!/usr/bin/env python3

# apt-get install -y python python-setuptools python-pip python-dev python-imaging imagemagick
# pip install picamera

#Imports
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

#############
### Debug ###
#############
# These options allow you to run a quick test of the app.
# Both options must be set to 'False' when running as proper photobooth
# Button will be pressed automatically, and app will exit after 1 photo cycle
TESTMODE_AUTOPRESS_BUTTON = False
# Reduced wait between photos and 2 photos only
TESTMODE_FAST = False

########################
### Variables Config ###
########################
# pin that the 'take photo' button is attached to
PIN_CAMERA_BTN = 18
# pin that the 'exit app' button is attached to (OPTIONAL BUTTON FOR EXITING THE APP)
PIN_EXIT_BTN = 24
# number of pics to be taken
TOTAL_PICS = 4
# number of seconds as users prepare to have photo taken
PREP_DELAY = 3
COUNTDOWN_FROM = 3
JPEG_QUALITY = 90
FINAL_REVIEW_DELAY = 5

# aspect 4:3 (camera max/2) (minor move on capture)
PHOTO_W, PHOTO_H = 1296, 972
# aspect 4:3 (camera max) (no move on capture) (tends to crash)
# PHOTO_W, PHOTO_H = 2592, 1944

if TESTMODE_FAST:
    # TOTAL_PICS = 2     # number of pics to be taken
    PREP_DELAY = 0     # number of seconds at step 1 as users prep to have photo taken
    COUNTDOWN_FROM = 0
    FINAL_REVIEW_DELAY = 1

##############################
### Setup Objects and Pins ###
##############################
#Setup GPIO
GPIO.setmode(GPIO.BCM)
GPIO.setup(PIN_CAMERA_BTN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(PIN_EXIT_BTN, GPIO.IN, pull_up_down=GPIO.PUD_UP)

#Setup Camera
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

####################
### Other Config ###
####################
REAL_PATH = os.path.dirname(os.path.realpath(__file__))

########################
### Helper Functions ###
########################
def print_overlay(string_to_print):
    """
    Writes a string to both [i] the console, and [ii] CAMERA.annotate_text
    """
    # debug("print_overlay(%s)" % string_to_print)
    # print string_to_print
    CAMERA.annotate_text = string_to_print

def get_base_filename_for_images():
    """
    For each photo-capture cycle, a common base filename shall be used,
    based on the current timestamp.

    Example:
    /photos/2017-12-31_23-59-59

    The example above, will later result in:
    /photos/2017-12-31_23-59-59_p1of4.png, being used as a filename.
    """
    debug("get_base_filename_for_images()")
    base_filename = '/photos/' + str(datetime.datetime.now()).split('.')[0]
    base_filename = base_filename.replace(' ', '_')
    base_filename = base_filename.replace(':', '')
    base_filename = base_filename.replace('-', '')
    # debug("get_base_filename_for_images() returning: %s" % base_filename)
    return base_filename

def remove_overlay(overlay_id):
    """
    If there is an overlay, remove it
    """
    debug("remove_overlay(%s)" % id(overlay_id))
    if overlay_id != -1:
        CAMERA.remove_overlay(overlay_id)

# overlay one image on screen
def overlay_image(image_path, duration=0, layer=3):
    """
    Add an overlay (and sleep for an optional duration).
    If sleep duration is not supplied, then overlay will need to be removed later.
    This function returns an overlay id, which can be used by remove_overlay(id).
    """
    f = "-- overlay_image(%s, %s, %s)" % (image_path, duration, layer)
    # print f

    # "The camera`s block size is 32x16 so any image data
    #  provided to a renderer must have a width which is a
    #  multiple of 32, and a height which is a multiple of
    #  16."
    #  Refer: http://picamera.readthedocs.io/en/release-1.10/recipes1.html#overlaying-images-on-the-preview

    # Load the arbitrarily sized image
    img = Image.open(REAL_PATH + image_path)

    # Create an image padded to the required size with
    # mode 'RGB'
    pad = Image.new('RGB', (
        ((img.size[0] + 31) // 32) * 32,
        ((img.size[1] + 15) // 16) * 16,
    ))

    # Paste the original image into the padded one
    pad.paste(img, (0, 0))

    #Get the padded image data
    try:
        padded_img_data = pad.tobytes()
    except AttributeError:
        padded_img_data = pad.tostring() # Note: tostring() is deprecated in PIL v3.x

    # Add the overlay with the padded image as the source,
    # but the original image's dimensions
    o_id = CAMERA.add_overlay(padded_img_data, size=img.size)
    o_id.layer = layer

    if duration > 0:
        sleep(duration)
        CAMERA.remove_overlay(o_id)
        # print "%s returning: -1" % f
        return -1 # '-1' indicates there is no overlay
    else:
        # print "%s returning: %s" % (f, id(o_id))
        return o_id # we have an overlay, and will need to remove it later

###############
### Screens ###
###############

def timed_overlay(overlay_key, filename_prefix=""):
    """
    """
    debug("timed_overlay(%s)" % overlay_key)
    overlay_cfg = {
        "pose1": (PREP_DELAY, "/assets/get_ready_1.jpg"),
        "pose2": (PREP_DELAY, "/assets/get_ready_2.jpg"),
        "pose3": (PREP_DELAY, "/assets/get_ready_3.jpg"),
        "pose4": (PREP_DELAY, "/assets/get_ready_4.jpg"),
        "processing": (2, "/assets/processing.jpg"),
        "done": (FINAL_REVIEW_DELAY, "/assets/all_done.jpg"),
        "2x2": (FINAL_REVIEW_DELAY, filename_prefix + "_2x2.jpg"),
        "1x4": (FINAL_REVIEW_DELAY, filename_prefix + "_1x4.jpg"),
    }
    seconds = overlay_cfg[overlay_key][0]
    image = overlay_cfg[overlay_key][1]
    overlay_image(image, seconds)

def take_photo(photo_number, filename_prefix):
    """
    This function captures the photo
    """
    debug("take_photo(%s, ...)" % (photo_number))

    #get filename to use
    filename = filename_prefix + '_p' + str(photo_number) + '.jpg'

    #countdown from X, and display countdown on screen
    for counter in range(COUNTDOWN_FROM, 0, -1):
        # push the number down to bottom of display
        print_overlay("\n\n\n\n" + str(counter))
        debug("take_photo(%s, waiting ...%s)" % (photo_number, counter))
        sleep(1)

    #Take still
    CAMERA.annotate_text = ''
    CAMERA.capture(REAL_PATH + filename)
    debug("take_photo(%s, ...) Saved %s" % (photo_number, filename))

def playback_singles(filename_prefix):
    """
    """
    debug("playback_singles(%s)" % filename_prefix)
    prev_overlay = False
    for photo_number in range(1, TOTAL_PICS + 1):
        filename = filename_prefix + '_p' + str(photo_number) + '.jpg'
        this_overlay = overlay_image(filename, False, 3+TOTAL_PICS)
        # The idea here, is only remove the previous overlay after a new overlay is added.
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
        input_filenames.append(filename_prefix + '_p' + str(i) + '.jpg')

    # Thumbnail size of pictures
    outer_border = math.floor(PHOTO_W / 50)
    inner_border = math.floor(PHOTO_W / 72)
    thumb_box = (
        int(PHOTO_W / 2),
        int(PHOTO_H / 2)
    )
    thumb_size = (
        int(thumb_box[0] - outer_border - inner_border) ,
        int(thumb_box[1] - outer_border - inner_border)
    )
    debug("%s Got vars" % f)

    # If template asset is found, use that for background.
    # Else, create output image with white background
    bg_glob='%s/assets/2x2_at_%sx%s*' % (REAL_PATH, PHOTO_W, PHOTO_H);
    bg_list = glob.glob(bg_glob)
    # debug("bg_list:")
    # debug(bg_list)
    bg_url = random.choice(bg_list)

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
    output_filename = filename_prefix + '_2x2.jpg'
    # output_image.save(REAL_PATH + output_filename, "JPEG")
    output_image.transpose(Image.FLIP_LEFT_RIGHT).save(REAL_PATH + output_filename, "JPEG", quality=JPEG_QUALITY)
    # overlay_image(output_filename, 3, 4)
    # return output_filename
    debug("%s took: %2.3fs" % (f, time.time() - s))

def assemble_1x4(filename_prefix):
    """Assembles four pictures into a 1x4 grid

    It assumes, all original pictures have the same aspect ratio as
    the resulting image.

    For the thumbnail sizes we have:
    h = (H - 2 * a - 2 * b) / 2
    w = (W - 2 * a - 2 * b) / 2

                       W
            |--------------------|
       ---  +---+------------+---+  ---
        |   |                    |   |
        |   |                    |   |  b
        |   |                    |   |
        |   |   +------------+   |  ---
        |   |   |            |   |   |
        |   |   |      0     |   |   |  h
        |   |   |            |   |   |
        |   |   +------------+   |  ---
        |   |                    |   |  a
        |   |   +------------+   |  ---
        |   |   |            |   |   |
        |   |   |      1     |   |   |  h
        |   |   |            |   |   |
        |   |   +------------+   |  ---
      H |   |                    |   |  a
        |   |   +------------+   |  ---
        |   |   |            |   |   |
        |   |   |      2     |   |   |  h
        |   |   |            |   |   |
        |   |   +------------+   |  ---
        |   |                    |   |  a
        |   |   +------------+   |  ---
        |   |   |            |   |   |
        |   |   |      3     |   |   |  h
        |   |   |            |   |   |
        |   |   +------------+   |  ---
        |   |                    |   |
        |   |                    |   |  c
        |   |                    |   |
       ---  +---+------------+---+  ---
            |---|------------|---|
              a        w       a
    """
    f = "-- assemble_1x4(%s)" % filename_prefix
    debug(f)

    input_filenames = []
    for i in range (1, TOTAL_PICS + 1):
        input_filenames.append(filename_prefix + '_p' + str(i) + '.jpg')

    # Thumbnail size of pictures
    border_px = 10 # a
    header_px = 50 # b
    footer_px = 300 # c
    thumb_box = (
        int(PHOTO_W / 2),
        int(PHOTO_H / 2)
    )
    bg_width = thumb_box[0] + (border_px * 2)
    bg_height = (thumb_box[1] * 4) + (border_px * (TOTAL_PICS - 1)) + header_px + footer_px
    bg_height = ((thumb_box[1] + border_px) * TOTAL_PICS) + header_px + footer_px - border_px

    debug("%s Got vars" % f)

    # If template asset is found, use that for background.
    # Else, create output image with white background
    bg_url='%s/assets/1x4_at_%sx%s.jpg' % (REAL_PATH, bg_width, bg_height);
    if os.path.isfile(bg_url):
        output_image = Image.open(bg_url)
        debug("%s Opened image %sx%s" % (f, bg_width, bg_height))
    else:
        output_image = Image.new('RGB', (bg_width, bg_height), (255, 255, 255))
        debug("%s Created new image %sx%s" % (f, bg_width, bg_height))

    for photo_number in range(0, 4):
        img = Image.open(REAL_PATH + input_filenames[photo_number])#.transpose(Image.FLIP_LEFT_RIGHT)
        debug("%s Loaded #%s" % (f, photo_number))
        # img.thumbnail(thumb_size)
        img.thumbnail(thumb_box)
        output_image.paste(img, (
            border_px,
            header_px + (photo_number * (thumb_box[1] + border_px))
        ))
        debug("%s Pasted #%s" % (f, photo_number))

    # Save assembled image
    output_filename = filename_prefix + '_1x4.jpg'
    # output_image.save(REAL_PATH + output_filename, "JPEG")
    output_image.transpose(Image.FLIP_LEFT_RIGHT).save(REAL_PATH + output_filename, "JPEG", quality=JPEG_QUALITY)
    # overlay_image(output_filename, 3, 4)
    # return output_filename


def main():
    """
    Main program loop
    """

    #Start Program
    debug("main() Welcome to the photo booth!")
    debug("main() Press the button to take a photo")

    #Start camera preview
    CAMERA.start_preview()

    # Display intro screen
    intro_image_1 = "/assets/intro_1.jpg"
    intro_image_2 = "/assets/intro_2.jpg"
    overlay_1 = overlay_image(intro_image_1, 0, 3)
    overlay_2 = overlay_image(intro_image_2, 0, 4)

    #Wait for someone to push the button
    i = 0
    blink_speed = 5
    while True:

        #Use falling edge detection to see if button is pushed
        pressed_snap = GPIO.wait_for_edge(PIN_CAMERA_BTN, GPIO.FALLING, timeout=100)
        pressed_exit = GPIO.wait_for_edge(PIN_EXIT_BTN, GPIO.FALLING, timeout=100)

        if pressed_exit is not None:
            return #Exit the photo booth

        if TESTMODE_AUTOPRESS_BUTTON:
            pressed_snap = True

        #Stay inside loop, until button is pressed
        if pressed_snap is None:

            #After every 5 cycles, alternate the overlay
            i = i + 1
            if i == blink_speed:
                overlay_2.alpha = 255
            elif i == (2 * blink_speed):
                overlay_2.alpha = 0
                i = 0

            #Regardless, restart loop
            continue

        # Button has been pressed!
        debug("main() Button pressed!")
        filename_prefix = get_base_filename_for_images()
        remove_overlay(overlay_2)
        remove_overlay(overlay_1)

        for photo_number in range(1, TOTAL_PICS + 1):
            # Show screen alerting user to pose
            timed_overlay("pose" + str(photo_number))
            # Take the photo
            take_photo(photo_number, filename_prefix)

        # FAKER
        # filename_prefix = "/photos/2017-12-13_19-29-48"

        # Show processing message prior to showing previews, it will block the camera
        overlay_3 = overlay_image("/assets/black.jpg", 0, 3)
        overlay_4 = overlay_image("/assets/processing.jpg", 0, 4)

        assemble_2x2(filename_prefix)
        # assemble_1x4(filename_prefix)

        remove_overlay(overlay_4)

        # playback_singles(filename_prefix)
        timed_overlay("2x2", filename_prefix)
        # timed_overlay("1x4", filename_prefix)

        remove_overlay(overlay_3)

        timed_overlay("done")

        # If we were doing a test run, exit here.
        if TESTMODE_AUTOPRESS_BUTTON:
            break

        # debug("main() freeing memory")
        # gc.collect()

        # Otherwise, display intro screen again
        overlay_1 = overlay_image(intro_image_1, 0, 3)
        overlay_2 = overlay_image(intro_image_2, 0, 4)
        debug("main() Press the button to take a photo")

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
