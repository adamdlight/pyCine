Implements a Python class for reading Vision Research cine files.

Requires: numpy, struct, sys, traceback, tables

Current implementation is rudimentary - just what I need to read Phantom v7.10 12-bit monochrome cine files and save them to HDF5 format.  I'd love to increase the functionality, so feel free to contribute!

Module can be run as a script to convert cine files directly to h5 files.  Structure of the resulting file is as follows.

The root group contains the data I use most: '/images' and '/time_float' (hard link)
There are two subgroups: 
'/Meta', contains all cine metadata from the CineFileHeader, BitmapInfoHeader, and Setup structures.
'/TaggedBlocks' contains all tagged block variables, such as time and exposure for each frame.

For more information about the cine file format, see <www.visionresearch.com/devzonedownloads/cine640.pdf>.

Note:  I started off using h5py, but as of commit eea6641948dd055cc375f63ddda15114b960b032 switched to pytables for hdf5 functionality.  I was having trouble making standalone executables for collaborators using pyinstaller with h5py.  
