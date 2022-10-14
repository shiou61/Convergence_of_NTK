# -*- coding: utf-8 -*-
"""batch64_adam1_deep10.ipynb

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/1VTozyjmOo4m7npk0JdQu3ez7nypOOF-T
"""

from psutil import virtual_memory
ram_gb = virtual_memory().total / 1e9
print('Your runtime has {:.1f} gigabytes of available RAM\n'.format(ram_gb))

if ram_gb < 20:
  print('Not using a high-RAM runtime')
else:
  print('You are using a high-RAM runtime!')

from google.colab import drive
drive.mount('/content/drive')

import jax.numpy as jnp
from jax import grad, jit
import jax.random
from jax.example_libraries import stax, optimizers
from jax import jacfwd, jacrev
from jax.nn import initializers

import numpy as np
import matplotlib.pyplot as plt

import tensorflow_datasets as tfds
from sklearn.model_selection import train_test_split

import math, random
import pickle


key = jax.random.PRNGKey(0)
"""Load dataset train and test datasets into memory."""
ds_builder = tfds.builder("cifar10", data_dir=None)
ds_builder.download_and_prepare()

def construct_dataset(ds_builder, sample_size, normalize=False, sample=False):
  train_data, train_labels = tfds.as_numpy(
        ds_builder.as_dataset(split="train", batch_size=-1, as_supervised=True, shuffle_files=True)
  )
  train_data = jnp.float32(train_data) / 255.0
  
  if sample:
    train_data, train_labels = sample_dataset(train_data=train_data, train_labels=train_labels, sample_size=sample_size)
  
  if normalize:
      train_data, mean, std = normalize_data(train_data)

  return train_data, train_labels

def normalize_data(data, mean=None, std=None):
    if mean is None or std is None:
        mean = jnp.mean(data, axis=[0, 1, 2])[jnp.newaxis, jnp.newaxis, jnp.newaxis, :]
        std = jnp.std(data, axis=[0, 1, 2])[jnp.newaxis, jnp.newaxis, jnp.newaxis, :]

    data = data - mean
    data = data / std
    return data, mean, std

def one_hot(x, k, dtype=jnp.float32):
    """Create a one-hot encoding of x of size k """
    return jnp.array(x[:, None] == jnp.arange(k), dtype)

def sample_dataset(train_data, train_labels, sample_size): 
  train_data_labels = []
  for i in range(train_data.shape[0]):
    train_data_labels.append((train_data[i], train_labels[i]))

  shuffled_train_data_labels = random.sample(train_data_labels, sample_size)

  shuffled_train_data = []
  shuffled_train_labels = []
  for i in range(len(shuffled_train_data_labels)):
    shuffled_train_data.append(shuffled_train_data_labels[i][0])
    shuffled_train_labels.append(shuffled_train_data_labels[i][1])
  
  return np.array(shuffled_train_data), np.array(shuffled_train_labels)  

def get_minibatch(batch_size, train_data, train_labels, seed, mlp=False):
  random.seed(seed)
  train_data_labels = []
  for i in range(train_data.shape[0]):
    train_data_labels.append([train_data[i], train_labels[i]])

  num_epoch = math.floor(len(train_data_labels) / batch_size)
  batched_train_ds = []

  batches = 0
  rest = train_data_labels

  for i in range(num_epoch):

    minibatch_ds = {}
    minibatch_data = []
    minibatch_labels = []

    if batch_size <= len(rest):
      batches, rest = train_test_split(rest, train_size=batch_size)
      for batch in batches:
        minibatch_data.append(batch[0])
        minibatch_labels.append(batch[1])
        
      minibatch_ds['data'] = minibatch_data
      minibatch_ds['labels'] = one_hot(jnp.array(minibatch_labels), k=10)

    if mlp:
      minibatch_ds["data"] = jnp.array([jnp.ravel(data) for data in minibatch_ds["data"]])

    batched_train_ds.append(minibatch_ds)
  
  return batched_train_ds 

def filter_gradients(gradients):
  gradients_filtered = []

  for grad in gradients:
    if grad:
      gradients_filtered.append(grad)

  return gradients_filtered

#Get Layerwise Outputwise Gram Matrix of Tangent Kernel at time
def get_gram_matrix_of_tangent_kernel_at_time_layerwise_outputwise(gradients, sample_size, output, layer):

  grads = filter_gradients(gradients)

  weight = 0
  bias = 1

  gram_matrix_layerwise_outputwise_elementwise = []
  w_grad = []
  b_grad = []

  for i in range(sample_size):

    w_grad.append(grads[layer][weight][i][output])
    b_grad.append(grads[layer][bias][i][output])


  for k in range(sample_size):
    for n in range(sample_size):
      w_grad_1 = jnp.ravel(w_grad[k])
      w_grad_2 = jnp.ravel(w_grad[n])

      b_grad_1 = b_grad[k]
      b_grad_2 = b_grad[n]

      value = jnp.dot(w_grad_1, w_grad_2) + jnp.dot(b_grad_1, b_grad_2)
      gram_matrix_layerwise_outputwise_elementwise.append(float(value))

  return gram_matrix_layerwise_outputwise_elementwise

#Get Layerwise Gram Matrix of Tangent Kernel at time
def get_layerwise_gram_matrix_of_tangent_kernel_at_time(gradients, sample_size, output_dim, layer):
  
  gram_matrix_layerwise = []

  for output in range(output_dim):

    gram_matrix_outputwise_layerwise = get_gram_matrix_of_tangent_kernel_at_time_layerwise_outputwise(gradients, sample_size, output, layer)
    
    gram_matrix_layerwise.append(gram_matrix_outputwise_layerwise)
  
  return gram_matrix_layerwise

#Get Gram Matrix of Tangent Kernel at time
def get_gram_matrix_of_tangent_kernel_at_time(gradients, sample_size, output_dim, layers):
  
  gram_matrix = []

  for output in range(output_dim):

    gram_matrix_outputwise = 0

    for layer in range(layers):

      gram_matrix_outputwise_layerwise = get_gram_matrix_of_tangent_kernel_at_time_layerwise_outputwise(gradients, sample_size, output, layer)
      gram_matrix_outputwise += jnp.array(gram_matrix_outputwise_layerwise)
    
    gram_matrix.append(gram_matrix_outputwise)
  
  return gram_matrix

#Get Layerwise Gram matrix of Path Kernel
def get_layerwise_gram_matrix_of_path_kernel(tangent_kernels_layerwise, output_dim, layer, training_steps):

  gram_matrix_layerwise = []

  for output in range(output_dim):

    gram_matrix_outputwise = 0

    for time in range(training_steps):
      gram_matrix_timewise_layerwise_outputwise = tangent_kernels_layerwise[time][layer][output]
      gram_matrix_outputwise += jnp.array(gram_matrix_timewise_layerwise_outputwise)
    
    gram_matrix_layerwise.append(gram_matrix_outputwise / training_steps)

  return gram_matrix_layerwise

#Get Gram_matrix of Path Kernel
def get_gram_matrix_of_path_kernel(tangent_kernels, output_dim, training_steps):

  gram_matrix = []

  for output in range(output_dim):

    gram_matrix_outputwise = 0

    for time in range(training_steps):
      gram_matrix_outputwise_timewise = tangent_kernels[time][output]
      gram_matrix_outputwise += jnp.array(gram_matrix_outputwise_timewise)
    
    gram_matrix.append(gram_matrix_outputwise / training_steps)

  return gram_matrix

#Kernel Alignment
def get_kernel_alignment(kernel_1, kernel_2, output_dim=10):

  denominator = 0
  neumerator_1 = 0
  neumerator_2 = 0

  for i in range(output_dim):
    gram_matrix_1 = jnp.array(kernel_1[i])
    gram_matrix_2 = jnp.array(kernel_2[i])

    denominator_outputwise = jnp.dot(gram_matrix_1, gram_matrix_2)
    neumerator_outputwise_1 = jnp.dot(gram_matrix_1, gram_matrix_1) 
    neumerator_outputwise_2 = jnp.dot(gram_matrix_2, gram_matrix_2)

    denominator += denominator_outputwise
    neumerator_1 += neumerator_outputwise_1
    neumerator_2 += neumerator_outputwise_2

  return denominator / (jnp.sqrt(neumerator_1) * jnp.sqrt(neumerator_2))

def get_kernel_perturbation(kernel_previous, kernel, kernel_next, output_dim=10):
  diff_with_previous = jnp.array(kernel) - jnp.array(kernel_previous)
  diff_with_next = jnp.array(kernel_next) - jnp.array(kernel)

  return get_kernel_alignment(diff_with_next, diff_with_previous)

def kernel_distance(kernel_1, kernel_2, output_dim=10):

  total = 0

  for i in range(output_dim):
    gram_matrix_1 = jnp.array(kernel_1[i])
    gram_matrix_2 = jnp.array(kernel_2[i])

    difference = gram_matrix_1 - gram_matrix_2

    total += jnp.dot(difference, difference)
  
  return total

batch_size = 64
std = 0.1
hidden_width = 100
last_hidden_width = 10
learning_rate = 0.1
epochs = 10
layers = 10
seed = 42
sample_size = 1000

#Don't press this code after second try
train_data, train_labels = construct_dataset(ds_builder=ds_builder, sample_size=sample_size, normalize=True, sample=True)
training_steps_accumulate = 0

#Define two-layer neural network
init_fn, apply_fn = stax.serial(
    stax.Dense(100, W_init=initializers.normal(stddev=std/math.sqrt(hidden_width)), b_init=initializers.normal(stddev=std/math.sqrt(hidden_width))), 
    stax.Relu,
    stax.Dense(100, W_init=initializers.normal(stddev=std/math.sqrt(hidden_width)), b_init=initializers.normal(stddev=std/math.sqrt(hidden_width))), 
    stax.Relu,
    stax.Dense(100, W_init=initializers.normal(stddev=std/math.sqrt(hidden_width)), b_init=initializers.normal(stddev=std/math.sqrt(hidden_width))), 
    stax.Relu,
    stax.Dense(100, W_init=initializers.normal(stddev=std/math.sqrt(hidden_width)), b_init=initializers.normal(stddev=std/math.sqrt(hidden_width))), 
    stax.Relu,
    stax.Dense(100, W_init=initializers.normal(stddev=std/math.sqrt(hidden_width)), b_init=initializers.normal(stddev=std/math.sqrt(hidden_width))), 
    stax.Relu,
    stax.Dense(100, W_init=initializers.normal(stddev=std/math.sqrt(hidden_width)), b_init=initializers.normal(stddev=std/math.sqrt(hidden_width))), 
    stax.Relu,
    stax.Dense(100, W_init=initializers.normal(stddev=std/math.sqrt(hidden_width)), b_init=initializers.normal(stddev=std/math.sqrt(hidden_width))), 
    stax.Relu,
    stax.Dense(100, W_init=initializers.normal(stddev=std/math.sqrt(hidden_width)), b_init=initializers.normal(stddev=std/math.sqrt(hidden_width))), 
    stax.Relu,
    stax.Dense(100, W_init=initializers.normal(stddev=std/math.sqrt(hidden_width)), b_init=initializers.normal(stddev=std/math.sqrt(hidden_width))), 
    stax.Relu,
    stax.Dense(10, W_init=initializers.normal(stddev=std/math.sqrt(last_hidden_width)), b_init=initializers.normal(stddev=std/math.sqrt(last_hidden_width))),
    stax.LogSoftmax
)

apply_fn = jit(apply_fn)

#Don't press this code after second try
_, params = init_fn(key, input_shape=(batch_size, 3072))
train_losses = []
tangent_kernels = [] #(time, outputs, dimension_gram_matrix)
path_kernels = []
kernel_alignments = [] #(time, alignments)
kernel_perturbations = [] #(time, perturbations)
kernel_distances = []
kernel_distances_perturbations = []

#define loss function
def loss(params, inputs, targets):
    # Unpack the input and targets
  inputs = inputs
  targets = targets
    
    # precdict the class using the neural network
  preds = apply_fn(params, inputs)

  return jnp.mean(-jnp.sum(targets * preds, axis=1))

  #Define gradient of loss
grad_loss = jit(lambda state, x, y: grad(loss)(get_params(state), x, y))

opt_init, opt_update, get_params = optimizers.adam(learning_rate)
#Hide this line after second try
opt_state_init = opt_init(params)
opt_update = jit(opt_update)



def train_continue(train_losses, tangent_kernels, path_kernels, kernel_perturbations, kernel_distances, kernel_distances_perturbations, train_data, train_labels, epochs, batch_size, sample_size,
                   opt_state, layers, training_steps_accumulate, output_dim, mlp=True, alignment=True, perturbation=True, distance=True, perturbation_distance=True):
  
  train_losses = train_losses
  tangent_kernels = tangent_kernels #(time, outputs, dimension_gram_matrix)
  path_kernels = path_kernels
  kernel_alignments = [] #(time, alignments)
  kernel_perturbations = kernel_perturbations
  kernel_distances = kernel_distances
  kernel_distances_perturbations = kernel_distances_perturbations

  training_steps_temp = epochs * math.floor(sample_size / batch_size)

  for t in range(epochs):
    train_ds = get_minibatch(batch_size=batch_size, train_data=train_data, train_labels=train_labels, mlp=mlp, seed=(42+t))

    for i in range(len(train_ds)):

      #update
      opt_state = opt_update(i, grad_loss(opt_state, train_ds[i]["data"], train_ds[i]["labels"]), opt_state)

      train_losses += [loss(get_params(opt_state), train_ds[i]["data"], train_ds[i]["labels"])]

      #print(f'Train loss: {loss(get_params(opt_state), train["data"], train["labels"])}')

      #Compute tangent kernels
      gradients = jit(jacrev(apply_fn))(get_params(opt_state), train_ds[i]["data"])
      filtered_gradients = filter_gradients(gradients)
      tangent_kernels.append(get_gram_matrix_of_tangent_kernel_at_time(gradients=filtered_gradients, sample_size=batch_size, output_dim=output_dim, layers=layers))
    
      path_kernel = get_gram_matrix_of_path_kernel(tangent_kernels=tangent_kernels, output_dim=output_dim, training_steps=(training_steps_accumulate+((t+1)*(i+1))))
      path_kernels.append(path_kernel)

    print(f'{t}' "th epoch done!")

  if alignment:
    for t in range(training_steps_temp + training_steps_accumulate):
      kernel_alignments.append(get_kernel_alignment(kernel_1=tangent_kernels[t], kernel_2=path_kernels[-1]))

  if perturbation:
    if training_steps_accumulate == 0:
      for t in range(training_steps_temp):
        if 2 <= t:
          kernel_perturbations.append(get_kernel_perturbation(kernel_previous=tangent_kernels[t-2 + training_steps_accumulate],
                                                         kernel=tangent_kernels[t-1 + training_steps_accumulate],
                                                         kernel_next=tangent_kernels[t + training_steps_accumulate]))
    else:
      for t in range(training_steps_temp):
        kernel_perturbations.append(get_kernel_perturbation(kernel_previous=tangent_kernels[t-2 + training_steps_accumulate],
                                                         kernel=tangent_kernels[t-1 + training_steps_accumulate],
                                                         kernel_next=tangent_kernels[t + training_steps_accumulate]))
  if distance:
    for t in range(training_steps_temp):
      kernel_distances.append(kernel_distance(kernel_1=tangent_kernels[t + training_steps_accumulate], kernel_2=path_kernels[t + training_steps_accumulate]))
  
  if perturbation_distance:
    if training_steps_accumulate == 0:
      for t in range(training_steps_temp):
        if 1 <= t:
          kernel_distances_perturbations.append(kernel_distance(kernel_1=tangent_kernels[t - 1 + training_steps_accumulate], kernel_2=tangent_kernels[t + training_steps_accumulate]))

    else:
      for t in range(training_steps_temp):
        kernel_distances_perturbations.append(kernel_distance(kernel_1=tangent_kernels[t - 1 + training_steps_accumulate], kernel_2=tangent_kernels[t + training_steps_accumulate]))

      
  training_steps_accumulate = training_steps_accumulate + training_steps_temp

  return train_losses, tangent_kernels, path_kernels, kernel_alignments, kernel_perturbations, opt_state, training_steps_accumulate, kernel_distances, kernel_distances_perturbations

train_losses, tangent_kernels, path_kernels, kernel_alignments, kernel_perturbations, opt_state, training_steps_accumulate, kernel_distances, kernel_distances_perturbations = train_continue(train_losses=train_losses, 
                                                                                                                                           tangent_kernels=tangent_kernels, 
                                                                                                                                           path_kernels=path_kernels, 
                                                                                                                                            
                                                                                                                                           kernel_perturbations=kernel_perturbations,
                                                                                                                                           kernel_distances=kernel_distances,
                                                                                                                                           kernel_distances_perturbations=kernel_distances_perturbations,
                                                                                                                                           train_data=train_data, 
                                                                                                                                           train_labels=train_labels, 
                                                                                                                                           epochs=epochs, 
                                                                                                                                           batch_size=batch_size, 
                                                                                                                                           sample_size=sample_size,

                   opt_state=opt_state_init, layers=layers, training_steps_accumulate=training_steps_accumulate, output_dim=10)

train_losses, tangent_kernels, path_kernels, kernel_alignments, kernel_perturbations, opt_state, training_steps_accumulate, kernel_distances, kernel_distances_perturbations = train_continue(train_losses=train_losses, 
                                                                                                                                           tangent_kernels=tangent_kernels, 
                                                                                                                                           path_kernels=path_kernels, 
                                                                                                                                            
                                                                                                                                           kernel_perturbations=kernel_perturbations,
                                                                                                                                           kernel_distances=kernel_distances,
                                                                                                                                           kernel_distances_perturbations=kernel_distances_perturbations,
                                                                                                                                           train_data=train_data, 
                                                                                                                                           train_labels=train_labels, 
                                                                                                                                           epochs=epochs, 
                                                                                                                                           batch_size=batch_size, 
                                                                                                                                           sample_size=sample_size,

                   opt_state=opt_state, layers=layers, training_steps_accumulate=training_steps_accumulate, output_dim=10)

len(path_kernels)

num_epoch = math.floor(sample_size/ batch_size)
total_epochs = training_steps_accumulate / num_epoch
epoch_ticks = [num_epoch * i  for i in range(int(total_epochs)) if i % 10 == 0]
epoch_ticks_labels = [str(i) for i in range(int(total_epochs)) if i % 10 == 0]

time_epochwise = range(0, training_steps_accumulate, num_epoch)
kernel_alignments_epochwise = []
train_losses_epochwise = []
kernel_distances_epochwise = []
kernel_perturbation_distances_epochwise = []
for t in time_epochwise:
  kernel_alignments_epochwise.append(kernel_alignments[int(t)])
  train_losses_epochwise.append(train_losses[int(t)])
  kernel_distances_epochwise.append(kernel_distances[int(t)])
  kernel_perturbation_distances_epochwise.append(kernel_distances_perturbations[int(t)])

time_epochwise_perturbation = np.arange(0, training_steps_accumulate-2, num_epoch)
kernel_perturbations_epochwise = []
for t in time_epochwise_perturbation:
  kernel_perturbations_epochwise.append(kernel_perturbations[int(t)])

#Alignments
fig, ax1= plt.subplots()
ax2 = ax1.twinx()

ax1.plot(time_epochwise, kernel_alignments_epochwise, color='red', label="Kernel Alignment")

ax1.set_xlabel('Epochs')
ax1.set_xticks(epoch_ticks)
ax1.set_xticklabels(epoch_ticks_labels)
ax1.set_ylabel('Kernel Alignment')
ax1.legend(loc='upper left', bbox_to_anchor=(0.3, 1))

ax2.plot(time_epochwise, train_losses_epochwise, label="Train Loss")

ax2.set_ylabel('Train Loss')
ax2.legend(loc='upper left', bbox_to_anchor=(0.7, 1))
plt.show

#perturbations
fig, ax = plt.subplots()

ax.plot(time_epochwise_perturbation, kernel_perturbations_epochwise, label="perturbation")

ax.set_xlabel('Epochs')
ax.set_xticks(epoch_ticks)
ax.set_xticklabels(epoch_ticks_labels)
ax.set_ylabel('Kernel Perturbation')
ax.legend()

plt.show

#distance t and t-1
fig, ax1= plt.subplots()
ax2 = ax1.twinx()

ax1.plot(time_epochwise, kernel_perturbation_distances_epochwise, color='green', label="Kernel Difference")

ax1.set_xlabel('Epochs')
ax1.set_xticks(epoch_ticks)
ax1.set_xticklabels(epoch_ticks_labels)
ax1.set_ylabel('Kernel Difference')
ax1.legend(loc='upper left', bbox_to_anchor=(0.3, 1))

ax2.plot(time_epochwise, train_losses_epochwise, label="Train Loss")

ax2.set_ylabel('Train Loss')
ax2.legend(loc='upper left', bbox_to_anchor=(0.7, 1))

plt.show

#Kernel Distance
fig, ax1= plt.subplots()
ax2 = ax1.twinx()

ax1.plot(time_epochwise, kernel_distances_epochwise, color="green", label="Kernel Distance")

ax1.set_xlabel('Epochs')
ax1.set_xticks(epoch_ticks)
ax1.set_xticklabels(epoch_ticks_labels)
ax1.set_ylabel('Kernel Distance')
ax1.legend(loc='upper left', bbox_to_anchor=(0.3, 1))

ax2.plot(time_epochwise, train_losses_epochwise, label="Train Loss")

ax2.set_ylabel('Train Loss')
ax2.legend(loc='upper left', bbox_to_anchor=(0.7, 1))

plt.show

#save data

opt_state_pickle = optimizers.unpack_optimizer_state(opt_state)
with open('/content/drive/MyDrive/batch64_adam1_deep10/opt_state.bin', 'wb') as f:
    pickle.dump(opt_state_pickle, f)

with open('/content/drive/MyDrive/batch64_adam1_deep10/tangent_kernels.bin', 'wb') as f:
    pickle.dump(tangent_kernels, f)

with open('/content/drive/MyDrive/batch64_adam1_deep10/path_kernels.bin', 'wb') as f:
    pickle.dump(path_kernels, f)

with open('/content/drive/MyDrive/batch64_adam1_deep10/train_losses.bin', 'wb') as f:
    pickle.dump(train_losses, f)

with open('/content/drive/MyDrive/batch64_adam1_deep10/kernel_alignments.bin', 'wb') as f:
    pickle.dump(kernel_alignments, f)

with open('/content/drive/MyDrive/batch64_adam1_deep10/kernel_distances.bin', 'wb') as f:
    pickle.dump(kernel_distances, f)

with open('/content/drive/MyDrive/batch64_adam1_deep10/kernel_distances_perturbations.bin', 'wb') as f:
    pickle.dump(kernel_distances_perturbations, f)

with open('/content/drive/MyDrive/batch64_adam1_deep10/kernel_perturbations.bin', 'wb') as f:
    pickle.dump(kernel_perturbations, f)

with open('/content/drive/MyDrive/batch64_adam1_deep10/training_steps_acumulate.bin', 'wb') as f:
    pickle.dump(training_steps_accumulate, f)

with open('/content/drive/MyDrive/batch64_adam1_deep10/train_data.bin', 'wb') as f:
  pickle.dump(train_data, f)

with open('/content/drive/MyDrive/batch64_adam1_deep10/train_labels.bin', 'wb') as f:
  pickle.dump(train_labels, f)

#read data
opt_state = optimizers.pack_optimizer_state(pickle.load(open('/content/drive/MyDrive/batch64_adam1/opt_state.bin', 'rb')))
tangent_kernels = pickle.load(open('/content/drive/MyDrive/batch64_adam1/tangent_kernels.bin', 'rb'))
train_losses = pickle.load(open('/content/drive/MyDrive/batch64_adam1/train_losses.bin', 'rb'))
path_kernels = pickle.load(open('/content/drive/MyDrive/batch64_adam1/path_kernels.bin', 'rb'))
kernel_alignments = pickle.load(open('/content/drive/MyDrive/batch64_adam1/kernel_alignments.bin', 'rb'))
kernel_distances = pickle.load(open('/content/drive/MyDrive/batch64_adam1/kernel_distances.bin', 'rb'))
kernel_distances_perturbations = pickle.load(open('/content/drive/MyDrive/batch64_adam1/kernel_distances_perturbations.bin', 'rb'))
kernel_perturbations = pickle.load(open('/content/drive/MyDrive/batch64_adam1/kernel_perturbations.bin', 'rb'))
training_steps_accumulate = pickle.load(open('/content/drive/MyDrive/batch64_adam1/training_steps_acumulate.bin', 'rb'))
train_data = pickle.load(open('/content/drive/MyDrive/batch64_adam1/train_data.bin', 'rb'))
train_labels = pickle.load(open('/content/drive/MyDrive/batch64_adam1/train_labels.bin', 'rb'))

