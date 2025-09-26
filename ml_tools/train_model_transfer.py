# train_model_transfer.py
import os
import numpy as np
import json
import matplotlib.pyplot as plt
import seaborn as sns
from PIL import Image
import traceback
import tensorflow as tf
from sklearn.utils import class_weight

# --- User-configurable parameters ---
IMG_SIZE = 128 # MobileNetV2 works well with various sizes, 128 is fine
TEST_SPLIT_PERCENTAGE = 0.2
BATCH_SIZE = 16
NUM_EPOCHS = 60 

# --- Directory setup ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATASET_DIR = os.path.join(SCRIPT_DIR, 'dataset')
MODEL_SAVE_DIR = os.path.join(SCRIPT_DIR, 'models')

def check_dependencies():
    """Checks for required libraries and provides installation instructions."""
    import importlib.util
    dependencies = {
        'tensorflow': 'tensorflow',
        'sklearn': 'scikit-learn',
        'matplotlib': 'matplotlib',
        'seaborn': 'seaborn',
        'numpy': 'numpy',
        'PIL': 'Pillow'
    }
    missing = []
    for package, install_name in dependencies.items():
        if importlib.util.find_spec(package) is None:
            missing.append(install_name)

    if missing:
        print("\n--- Required Libraries Missing ---")
        print("Please install the following packages to run this script:")
        print(f"pip install {' '.join(missing)}")
        print("---------------------------------\n")
        return False
    return True

def load_and_preprocess_images():
    """Loads images from the dataset directory and preprocesses them."""
    images = []
    labels = []
    class_names = sorted([d for d in os.listdir(DATASET_DIR) if os.path.isdir(os.path.join(DATASET_DIR, d))])

    if not class_names:
        print(f"Error: No subdirectories (classes) found in '{DATASET_DIR}'.")
        print("Please create subdirectories for each image class and add your images there.")
        return None, None, None

    print(f"Found {len(class_names)} classes: {class_names}")

    for class_index, class_name in enumerate(class_names):
        class_dir = os.path.join(DATASET_DIR, class_name)
        for filename in os.listdir(class_dir):
            if filename.lower().endswith(('.png', '.jpg', '.jpeg')):
                try:
                    img_path = os.path.join(class_dir, filename)
                    with Image.open(img_path) as img:
                        img = img.convert('RGB')
                        img = img.resize((IMG_SIZE, IMG_SIZE))
                        images.append(np.array(img))
                        labels.append(class_index)
                except Exception as e:
                    print(f"Warning: Could not load image {filename}. Error: {e}")

    if not images:
        print("Error: No images were successfully loaded from the dataset directory.")
        return None, None, None

    images = np.array(images, dtype='float32') / 255.0
    labels = np.array(labels)
    
    return images, labels, class_names

def plot_training_history(history):
    """Plots and saves the training and validation accuracy and loss."""
    acc = history.history['accuracy']
    val_acc = history.history['val_accuracy']
    loss = history.history['loss']
    val_loss = history.history['val_loss']
    epochs_range = range(len(acc))

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))
    fig.suptitle('Model Training Performance')

    ax1.plot(epochs_range, acc, label='Training Accuracy')
    ax1.plot(epochs_range, val_acc, label='Validation Accuracy')
    ax1.legend(loc='lower right')
    ax1.set_title('Training and Validation Accuracy')
    ax1.set_xlabel('Epoch')
    ax1.set_ylabel('Accuracy')

    ax2.plot(epochs_range, loss, label='Training Loss')
    ax2.plot(epochs_range, val_loss, label='Validation Loss')
    ax2.legend(loc='upper right')
    ax2.set_title('Training and Validation Loss')
    ax2.set_xlabel('Epoch')
    ax2.set_ylabel('Loss')

    save_path = os.path.join(MODEL_SAVE_DIR, 'training_performance.png')
    plt.savefig(save_path)
    print(f"\nSaved training performance plot to: {save_path}")
    plt.close(fig) # <-- CHANGE: Close the figure to prevent display issues

def plot_confusion_matrix(y_true, y_pred, class_names):
    """Plots and saves a confusion matrix."""
    from sklearn.metrics import confusion_matrix
    cm = confusion_matrix(y_true, y_pred)
    
    plt.figure(figsize=(10, 8))
    sns.heatmap(cm, annot=True, fmt='d', cmap='Blues', xticklabels=class_names, yticklabels=class_names)
    plt.title('Confusion Matrix')
    plt.ylabel('Actual Label')
    plt.xlabel('Predicted Label')
    
    save_path = os.path.join(MODEL_SAVE_DIR, 'confusion_matrix.png')
    plt.savefig(save_path)
    print(f"Saved confusion matrix plot to: {save_path}")
    plt.close() # <-- CHANGE: Close the figure

def create_transfer_model(num_classes):
    """Creates a transfer learning model using MobileNetV2."""
    from tensorflow.keras.models import Sequential
    from tensorflow.keras.layers import Input, Dense, Dropout, GlobalAveragePooling2D, Rescaling
    from tensorflow.keras.optimizers import Adam
    from tensorflow.keras.applications import MobileNetV2
    import tensorflow as tf

    # 1. Load the pre-trained base model (MobileNetV2) without its top classification layer
    base_model = MobileNetV2(
        input_shape=(IMG_SIZE, IMG_SIZE, 3),
        include_top=False,  # Crucial for transfer learning
        weights='imagenet'
    )

    # 2. Freeze the weights of the base model so they don't get updated during initial training
    base_model.trainable = False

    if num_classes == 2:
        final_activation = 'sigmoid'
        output_units = 1
        loss_function = 'binary_crossentropy'
    else:
        final_activation = 'softmax'
        output_units = num_classes
        loss_function = 'sparse_categorical_crossentropy'

    # 3. Build the new model on top of the base model
    model = Sequential([
        Input(shape=(IMG_SIZE, IMG_SIZE, 3)),
        
        # Data augmentation layers
        tf.keras.layers.RandomFlip("horizontal"),
        tf.keras.layers.RandomRotation(0.1),
        tf.keras.layers.RandomZoom(0.1),

        # The MobileNetV2 model expects pixel values in the [-1, 1] range.
        # Your load function scales to [0, 1], so this layer handles the conversion.
        Rescaling(1./127.5, offset=-1),
        
        # The frozen base model
        base_model,
        
        # New classification head
        GlobalAveragePooling2D(), # Efficiently flattens the feature maps
        Dropout(0.3),             # Regularization
        Dense(output_units, activation=final_activation)
    ])
    
    model.compile(optimizer=Adam(learning_rate=0.001),
                  loss=loss_function,
                  metrics=['accuracy'])
    
    return model

def main():
    """Main function to run the transfer learning training process."""
    print("\n--- Limbus ML Model Trainer (Transfer Learning) ---")
    if not check_dependencies(): return

    from sklearn.model_selection import train_test_split
    from tensorflow.keras.callbacks import EarlyStopping, ReduceLROnPlateau

    images, labels, class_names = load_and_preprocess_images()
    if images is None: return

    num_classes = len(class_names)
    print(f"Loaded {len(images)} images from {num_classes} classes.")
    
    if num_classes < 2:
        print("Error: At least two classes are required for training.")
        return

    X_train, X_val, y_train, y_val = train_test_split(
        images, labels, test_size=TEST_SPLIT_PERCENTAGE, random_state=42, stratify=labels
    )
    print(f"Training set size: {len(X_train)}")
    print(f"Validation set size: {len(X_val)}")

    #TODO TEST: Class weights are usually less critical with transfer learning
    #TODO     : because the model is more robust, but you can still add them here if needed.

    class_labels = np.unique(y_train)
    class_weights_array = class_weight.compute_class_weight(
        class_weight='balanced',
        classes=class_labels,
        y=y_train
    )
    class_weights_dict = dict(enumerate(class_weights_array))
    print(f"Calculated class weights: {class_weights_dict}")

    model = create_transfer_model(num_classes)
    model.summary()

    os.makedirs(MODEL_SAVE_DIR, exist_ok=True)
    label_map = {i: name for i, name in enumerate(class_names)}
    map_path = os.path.join(MODEL_SAVE_DIR, 'label_map.json')
    with open(map_path, 'w') as f:
        json.dump(label_map, f, indent=2)
    print(f"Saved label map to '{map_path}'\n")

    early_stopping = EarlyStopping(monitor='val_loss', patience=10, restore_best_weights=True)
    reduce_lr = ReduceLROnPlateau(monitor='val_loss', factor=0.2, patience=5, min_lr=1e-6, verbose=1)

    print("Starting initial training [feature extraction]...")
    history = model.fit(
        X_train, y_train,
        epochs=NUM_EPOCHS,
        batch_size=BATCH_SIZE,
        validation_data=(X_val, y_val),
        callbacks=[early_stopping, reduce_lr],
        class_weight=class_weights_dict,
        verbose=2
    )

    print("\nStarting fine-tuning...")
    # 1. Unfreeze the base model.
    # We can unfreeze the whole model or just the top layers. Let's unfreeze the top third.
    base_model = model.layers[4] # This gets the MobileNetV2 layer
    base_model.trainable = True
    
    # How many layers to keep frozen
    fine_tune_at = 100 # Let's fine-tune from layer 100 onwards
    
    # Freeze all the layers before the `fine_tune_at` layer
    for layer in base_model.layers[:fine_tune_at]:
        layer.trainable = False
        
    # 2. Re-compile the model with a very low learning rate.
    model.compile(
        optimizer=tf.keras.optimizers.Adam(learning_rate=1e-5), # Use a much smaller learning rate
        loss='sparse_categorical_crossentropy',
        metrics=['accuracy']
    )
    
    model.summary() # Print the new summary to see trainable params
    
    # 3. Continue training for a few more epochs.
    fine_tune_epochs = 40 # How many epochs to fine-tune for
    total_epochs = history.epoch[-1] + 1 + fine_tune_epochs
    
    history_fine = model.fit(
        X_train, y_train,
        epochs=total_epochs,
        initial_epoch=history.epoch[-1] + 1, # Resume from where the previous training stopped
        batch_size=BATCH_SIZE,
        validation_data=(X_val, y_val),
        callbacks=[early_stopping, reduce_lr],
        class_weight=class_weights_dict,
        verbose=2
    )
    
    # Combine the history objects to plot the full training run
    history.history['accuracy'].extend(history_fine.history['accuracy'])
    history.history['val_accuracy'].extend(history_fine.history['val_accuracy'])
    history.history['loss'].extend(history_fine.history['loss'])
    history.history['val_loss'].extend(history_fine.history['val_loss'])


    print("\nTraining complete!")
    best_epoch_idx = np.argmin(history.history['val_loss'])
    print(f"Best validation loss: {history.history['val_loss'][best_epoch_idx]:.4f} (Epoch {best_epoch_idx+1})")
    print(f"Best validation accuracy: {history.history['val_accuracy'][best_epoch_idx]:.4f}")

    model_path = os.path.join(MODEL_SAVE_DIR, 'limbus_classifier.keras')
    model.save(model_path)
    print(f"Model saved to '{model_path}'")
    
    plot_training_history(history)
    
    y_pred_probs = model.predict(X_val)
    if num_classes == 2:
        y_pred_classes = (y_pred_probs > 0.5).astype("int32").flatten()
    else:
        y_pred_classes = np.argmax(y_pred_probs, axis=1)

    plot_confusion_matrix(y_val, y_pred_classes, class_names)

if __name__ == '__main__':
    try:
        main()
    except ImportError:
        pass
    except Exception as e:
        print(f"\nAn unexpected error occurred: {e}")
        traceback.print_exc()