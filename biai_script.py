import os
import cv2
import keras
import numpy as np
import matplotlib.pyplot as plt
import segmentation_models as sm

# Loading dataset
if not os.path.exists('./dataset/'):
    os.system('git clone https://github.com/PanJan44/BIAI-dataset ./dataset')

# Directory paths
directories = {
    'x_train_dir': os.path.join('./dataset/Images', 'Train'),
    'y_train_dir': os.path.join('./dataset/Masks', 'Train'),
    'x_valid_dir': os.path.join('./dataset/Images', 'Train'),
    'y_valid_dir': os.path.join('./dataset/Masks', 'Train'),
    'x_test_dir': os.path.join('./dataset/Images', 'Train'),
    'y_test_dir': os.path.join('./dataset/Masks', 'Train')
}

# Resize and save images
width, height = 800, 600
min_size = 480

assert width >= min_size
assert height >= min_size

for dir_path in directories.values():
    for subdir, _, files in os.walk(dir_path):
        for file in files:
            path = os.path.join(subdir, file)
            img = cv2.imread(path)
            resized = cv2.resize(img, (width, height))
            os.remove(path)
            write_path = os.path.splitext(path)[0] + '.png'
            cv2.imwrite(write_path, resized)


# Utility function for data visualization
def visualize_and_denormalize(**images):
    """Plot and denormalize images in one row."""
    n = len(images)
    plt.figure(figsize=(30, 10))
    for i, (name, image) in enumerate(images.items()):
        plt.subplot(2, 3, i + 1)
        plt.xticks([])
        plt.yticks([])
        plt.title(' '.join(name.split('_')).title())

        # Denormalize image
        x_max = np.percentile(image, 98)
        x_min = np.percentile(image, 2)
        image = (image - x_min) / (x_max - x_min)
        image = image.clip(0, 1)

        plt.imshow(image)
    plt.show()

# classes for data loading and preprocessing
class Dataset:
    """CamVid Dataset. Read images, apply augmentation and preprocessing transformations.

    Args:
        images_dir (str): path to images folder
        masks_dir (str): path to segmentation masks folder
        class_values (list): values of classes to extract from segmentation mask
        augmentation (albumentations.Compose): data transfromation pipeline
            (e.g. flip, scale, etc.)
        preprocessing (albumentations.Compose): data preprocessing
            (e.g. noralization, shape manipulation, etc.)

    """

    CLASSES = {'nonmaskingbackground' : np.array([0, 0, 255]), 'maskingbackground' : np.array([0, 255, 0]),
               'animal' : np.array([255, 0, 0]), 'nonmaskingforegroundattention' : np.array([255, 255, 255]),
               'unlabelled' : np.array([0, 0, 0])}

    def __init__(
            self,
            images_dir,
            masks_dir,
            classes=None,
            augmentation=None,
            preprocessing=None,
    ):
        self.ids = os.listdir(images_dir)
        self.images_fps = [os.path.join(images_dir, image_id) for image_id in self.ids]
        self.masks_fps = [os.path.join(masks_dir, image_id) for image_id in self.ids]

        # convert str names to class values on masks
        self.class_colors = [self.CLASSES.get(key) for key in classes]

        self.augmentation = augmentation
        self.preprocessing = preprocessing

    def __getitem__(self, i):

        # read data
        image = cv2.imread(self.images_fps[i])
        image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        mask = cv2.imread(self.masks_fps[i])

        # extract certain classes from mask (e.g. cars)
        masks = [(mask == c).all(axis=2) for c in self.class_colors]
        mask = np.stack(masks, axis=-1).astype('float')

        # apply augmentations
        if self.augmentation:
            sample = self.augmentation(image=image, mask=mask)
            image, mask = sample['image'], sample['mask']

        # apply preprocessing
        if self.preprocessing:
            sample = self.preprocessing(image=image, mask=mask)
            image, mask = sample['image'], sample['mask']

        return image, mask

    def __len__(self):
        return len(self.ids)


class Dataloder(keras.utils.Sequence):
    """Load data from dataset and form batches

    Args:
        dataset: instance of Dataset class for image loading and preprocessing.
        batch_size: Integet number of images in batch.
        shuffle: Boolean, if `True` shuffle image indexes each epoch.
    """

    def __init__(self, dataset, batch_size=1, shuffle=False):
        self.dataset = dataset
        self.batch_size = batch_size
        self.shuffle = shuffle
        self.indexes = np.arange(len(dataset))

        self.on_epoch_end()

    def __getitem__(self, i):

        # collect batch data
        start = i * self.batch_size
        stop = (i + 1) * self.batch_size
        data = []
        for j in range(start, stop):
            data.append(self.dataset[j])

        # transpose list of lists
        batch = [np.stack(samples, axis=0) for samples in zip(*data)]

        return batch

    def __len__(self):
        """Denotes the number of batches per epoch"""
        return len(self.indexes) // self.batch_size

    def on_epoch_end(self):
        """Callback function to shuffle indexes each epoch"""
        if self.shuffle:
            self.indexes = np.random.permutation(self.indexes)

# Lets look at data we have
dataset = Dataset(x_train_dir, y_train_dir, classes=['nonmaskingbackground', 'maskingbackground', 'animal',
               'nonmaskingforegroundattention', 'unlabelled'])

image, mask = dataset[20] # get some sample

visualize(
    image=image,
    non_masking_background=mask[..., 0],
    masking_background=mask[..., 1],
    animal=mask[..., 2],
    non_masking_foreground_attention=mask[..., 3],
    unlabelled=mask[..., 4])

"""### Augmentations"""

import albumentations as A

def round_clip_0_1(x, **kwargs):
    return x.round().clip(0, 1)

# define heavy augmentations
def get_training_augmentation():
    train_transform = [

        A.HorizontalFlip(p=0.5),

        A.ShiftScaleRotate(scale_limit=0.5, rotate_limit=0, shift_limit=0.1, p=1, border_mode=0),

        A.PadIfNeeded(min_height=min_size, min_width=min_size, always_apply=True, border_mode=0),
        A.RandomCrop(height=min_size, width=min_size, always_apply=True),

        A.IAAAdditiveGaussianNoise(p=0.2),
        A.IAAPerspective(p=0.5),

        A.OneOf(
            [
                A.CLAHE(p=1),
                A.RandomBrightness(p=1),
                A.RandomGamma(p=1),
            ],
            p=0.9,
        ),

        A.OneOf(
            [
                A.IAASharpen(p=1),
                A.Blur(blur_limit=3, p=1),
                A.MotionBlur(blur_limit=3, p=1),
            ],
            p=0.9,
        ),

        A.OneOf(
            [
                A.RandomContrast(p=1),
                A.HueSaturationValue(p=1),
            ],
            p=0.9,
        ),
        A.Lambda(mask=round_clip_0_1)
    ]
    return A.Compose(train_transform)


def get_validation_augmentation(width, height):
    """Add paddings to make image shape divisible by 32"""
    if width % 32 != 0:
      width += 32 - width % 32
    if height % 32 != 0:
      height += 32 - height % 32

    test_transform = [
        A.PadIfNeeded(height, width)
    ]
    return A.Compose(test_transform)

def get_preprocessing(preprocessing_fn):
    """Construct preprocessing transform

    Args:
        preprocessing_fn (callbale): data normalization function
            (can be specific for each pretrained neural network)
    Return:
        transform: albumentations.Compose

    """

    _transform = [
        A.Lambda(image=preprocessing_fn),
    ]
    return A.Compose(_transform)

# Lets look at augmented data we have
dataset = Dataset(x_train_dir, y_train_dir, classes=['nonmaskingbackground', 'maskingbackground', 'animal',
               'nonmaskingforegroundattention', 'unlabelled'], augmentation=get_training_augmentation())

image, mask = dataset[42] # get some sample
visualize(
    image=image,
    non_masking_background=mask[..., 0],
    masking_background=mask[..., 1],
    animal=mask[..., 2],
    non_masking_foreground_attention=mask[..., 3],
    unlabelled=mask[..., 4])

"""# Segmentation model training"""

BACKBONE = 'efficientnetb3'
BATCH_SIZE = 8
CLASSES = ['animal']
LR = 0.0001
EPOCHS = 1

preprocess_input = sm.get_preprocessing(BACKBONE)

# define network parameters
n_classes = 1 if len(CLASSES) == 1 else len(CLASSES)  # case for binary and multiclass segmentation
activation = 'sigmoid' if n_classes == 1 else 'softmax'

#create model
model = sm.Unet(BACKBONE, classes=n_classes, activation=activation)

# define optomizer
optim = keras.optimizers.Adam(LR)

# Segmentation models losses can be combined together by '+' and scaled by integer or float factor
dice_loss = sm.losses.DiceLoss()
focal_loss = sm.losses.BinaryFocalLoss() if n_classes == 1 else sm.losses.CategoricalFocalLoss()
total_loss = dice_loss + (1 * focal_loss)

# actulally total_loss can be imported directly from library, above example just show you how to manipulate with losses
# total_loss = sm.losses.binary_focal_dice_loss # or sm.losses.categorical_focal_dice_loss

metrics = [sm.metrics.IOUScore(threshold=0.5), sm.metrics.FScore(threshold=0.5)]

# compile keras model with defined optimozer, loss and metrics
model.compile(optim, total_loss, metrics)

# Dataset for train images
train_dataset = Dataset(
    x_train_dir,
    y_train_dir,
    classes=CLASSES,
    augmentation=get_training_augmentation(),
    preprocessing=get_preprocessing(preprocess_input),
)

# Dataset for validation images
valid_dataset = Dataset(
    x_valid_dir,
    y_valid_dir,
    classes=CLASSES,
    augmentation=get_validation_augmentation(width, height),
    preprocessing=get_preprocessing(preprocess_input),
)

train_dataloader = Dataloder(train_dataset, batch_size=BATCH_SIZE, shuffle=True)
valid_dataloader = Dataloder(valid_dataset, batch_size=1, shuffle=False)

# check shapes for errors
assert train_dataloader[0][0].shape == (BATCH_SIZE, min_size, min_size, 3)
assert train_dataloader[0][1].shape == (BATCH_SIZE, min_size, min_size, n_classes)


# define callbacks for learning rate scheduling and best checkpoints saving
callbacks = [
    keras.callbacks.ModelCheckpoint('./best_model.h5', save_weights_only=True, save_best_only=True, mode='min'),
    keras.callbacks.ReduceLROnPlateau(),
]

# train model
history = model.fit_generator(
    train_dataloader,
    steps_per_epoch=len(train_dataloader),
    epochs=EPOCHS,
    callbacks=callbacks,
    validation_data=valid_dataloader,
    validation_steps=len(valid_dataloader),
)

# Plot training & validation iou_score values
plt.figure(figsize=(30, 5))
plt.subplot(121)
plt.plot(history.history['iou_score'])
plt.plot(history.history['val_iou_score'])
plt.title('Model iou_score')
plt.ylabel('iou_score')
plt.xlabel('Epoch')
plt.legend(['Train', 'Test'], loc='upper left')

# Plot training & validation loss values
plt.subplot(122)
plt.plot(history.history['loss'])
plt.plot(history.history['val_loss'])
plt.title('Model loss')
plt.ylabel('Loss')
plt.xlabel('Epoch')
plt.legend(['Train', 'Test'], loc='upper left')
plt.show()

"""# Model Evaluation"""

test_dataset = Dataset(
    x_test_dir,
    y_test_dir,
    classes=CLASSES,
    augmentation=get_validation_augmentation(width, height),
    preprocessing=get_preprocessing(preprocess_input),
)

test_dataloader = Dataloder(test_dataset, batch_size=1, shuffle=False)

# load best weights
model.load_weights('best_model.h5')

scores = model.evaluate_generator(test_dataloader)

print("Loss: {:.5}".format(scores[0]))
for metric, value in zip(metrics, scores[1:]):
    print("mean {}: {:.5}".format(metric.__name__, value))

"""# Visualization of results on test dataset"""

n = 5
ids = np.random.choice(np.arange(len(test_dataset)), size=n)

for i in ids:

    image, gt_mask = test_dataset[i]
    image = np.expand_dims(image, axis=0)
    pr_mask = model.predict(image).round()

    visualize(
        image=denormalize(image.squeeze()),
        gt_mask=gt_mask[..., 0].squeeze(),
        pr_mask=pr_mask[..., 0].squeeze(),
    )