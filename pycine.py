"""
This code is released under the terms of the GNU General Public License (GPL) version 3.

Author: Adam D. Light
Contact: adamdlight [at] gmail.com
Latest update: 08 January, 2012
"""

import struct
import numpy
import h5py

class Cine(object):
	"""
	Cine is a data container class that allows direct access 
	to image data and metadata in Vision Research .cine files.

	The structure of the object reflects the structure of the 
	cine file, as laid out in:
		<www.visionresearch.com/devzonedownloads/cine640.pdf>	

	Cine objects contain by default four dictionary attributes
	and one numpy.ndarray() attribute:
	
	cine_instance.CineFileHeader:
	        Dictionary containing the relevant fields from 
	        the CineFileHeader structure.  Fields include
	        byte offsets for chunks of the file, absolute
	        trigger time, number of images and trigger location
	        in original recording, number of images in file, etc.

	cine_instance.BitmapInfoHeader:
	        Dictionary containing the relevant fields from 
	        the BitmapInfoHeader structure.  Fields include 
	        image dimensions, bytes per image, bit depth of 
	        recording, physical size of pixels, etc. for use
	        in Windows image headers.

	cine_instance.Setup:
	        Dictionary containing the relevant fields from 
	        the Setup structure (settings used to make recording).  
	        Fields include image dimensions, camera details, 
	        bit depth of pixels, calibration data, acquisition
	        details, software and hardware versions, etc.

	cine_instance.TaggedBlocks:
	        Dictionary containing any tagged blocks present.
	        Each block type corresponds to a different data
	        type, so the blocks are collected into a dictionary.
	        Currently, only TimeOnly(1002) and ExposureOnly(1003)
	        blocks are supported.  If no tagged blocks are present
	        this attribute is of type None.  If desired, this 
	        attribute may be suppressed and the corresponding
	        section of the file may be skipped by setting the flag
	        'no_tagged_blocks = 1' on initialization.

	cine_instance.images:
	        Numpy ndarray((nx,ny,nframes),float) containing the 
	        image pixel data.   
	

	An instance of the class also creates a named attribute
	corresponding to each dictionary item.  The named attributes 
	may be disabled if desired using the flag 'no_attributes = 1' 
	on initialization.
	
	Error checking is very rudimentary.  The file i/o is wrapped
	in a WITH statement to give more foolproof interaction with 
	the binary file.

	The read routines use first two bytes 'CI' as a check on 
	whether the file is actually a cine file and the Mark field 
	of the Setup structure 'ST' to check that the byte structure 
	is correct.
	
	NOTE: Be aware of the difference in 1./Setup["FrameRate"] and 
	time_float[1] - time_float[0], as well as the difference between 
	TaggedBlocks["exposure_float"] and Setup["ShutterNs"].  According to 
	the data read directly from PCC version 2.0.717.0, the float values
	are more accurate.  Apparently, the nice integer values are the
	settings in the program, and the floating values are the actual
	hardware timing.
 
    """
	
	def __init__(self,filename,**kwargs):
        #may want to put in a feature to search or open dialog
        #open cine file for reading binary
		with open(filename,"rb") as cinefile:
			print "Reading cine file "+str(filename)
			filetype = struct.unpack('<2s',cinefile.read(2))[0]
			cinefile.seek(0) #return to top of file for reading
			assert filetype == 'CI', \
			    "File is not standard .cine format or file is corrupt."
			self._read_cine(cinefile,**kwargs)
            
	def _read_cine(self,cinefile,no_tagged_blocks=False,
		       no_attributes=False,read_images=True,
		       framelimits=None):
		# first 44 bytes are file header
		header_length = 44
		# next 40 bytes are bitmap header
		bitmapinfo_length = 40
		self.CineFileHeader = self._get_CineFileHeader(
			cinefile.read(header_length))
		self.BitmapInfoHeader = self._get_BitmapInfoHeader(
			cinefile.read(bitmapinfo_length))
		# next 6904 bytes are the setup structure
		deprecated_skip = 140  
		# next 140 bytes are deprecated info that's not correct,
		#     except for TrigFrame, which is only for syncing display in PCC
		cinefile.seek(header_length+bitmapinfo_length+deprecated_skip)  
		# check that setup is at correct Mark location
		setupstring = struct.unpack("<2s",cinefile.read(2))[0]
		if not (setupstring == 'ST'):
			print setupstring
			print "SETUP structure marker is incorrect."
			print "File format may have changed or file may be damaged."
		# get the length of the entire Setup structure
		setup_length = struct.unpack("<H",cinefile.read(2))[0]
		# skip the parameters from Mark up to ImWidth, since they are not  
		#     useful for normal camera data analysis (options not used)
		# start at ImWidth parameter, 597 bytes past beginning of structure
		setup_initial_skip = 597 
		new_setup_start_position = header_length + bitmapinfo_length\
		    + deprecated_skip+setup_initial_skip
		cinefile.seek(new_setup_start_position)
		# hard-code number of zeros in "zero area of the SETUP structure"  
		#     since rest of format is hard-coded anyway
		setup_zeros_length = 1212
		setup_read_length = setup_length - setup_initial_skip \
		    - setup_zeros_length - deprecated_skip
		# read Setup structure
		self.Setup = self._get_Setup(cinefile.read(setup_read_length))
		# scan to end of Setup structure (zeros present after data)
		cinefile.seek(header_length+bitmapinfo_length+setup_length)
		
		# read any tagged blocks
		if no_tagged_blocks:
			self.TaggedBlocks = {}
		else:
			tag_start = setup_length+header_length+bitmapinfo_length
			self.TaggedBlocks = self._get_TaggedBlocks(cinefile,tag_start,framelimits)     
			
		if read_images:
			# Read image data
			self.images = self._get_Images(cinefile,
						       self.CineFileHeader["OffImageOffsets"],
						       framelimits)
		

		if no_attributes:
			return
		else:
			# Define object attributes corresponding to each dictionary entry
			# (for convenience) 
			for key,value in self.CineFileHeader.iteritems():
				setattr(self,key,value)
			for key,value in self.BitmapInfoHeader.iteritems():
				setattr(self,key,value)
			for key,value in self.Setup.iteritems():
				setattr(self,key,value)
			for key,value in self.TaggedBlocks.iteritems():
				setattr(self,key,value)
			return
		
    
    
	# DEFINE METHODS FOR READING DIFFERENT PIECES OF THE FILE
				
	def _get_CineFileHeader(self,filestring):
		"""Takes output from cinefile.read(), parses it using struct.unpack()
		according to 
		<www.visionresearch.com/devzonedownloads/cine640.pdf>,
		and returns a dictionary of values for the CineFileHeader structure.
		
		Parse first 44 bytes via hardcoded content order and size:
		This process produces, for example:
		In [88]: struct.unpack('<2sHHHl',cinefile.read(12))
		Out[88]: ('CI', 44, 0, 1, -348756)
		Where the tuple entries correspond to the fields 
		(as defined at www.visionresearch.com/devzonedownloads/cine640.pdf):
		(Type, Headersize, Compression, Version, FirstMovieImage)
		
		The format comes from the struct python module and reads as follows:
		< means little endian
		2s means a two-character string
		H means an unsigned, 2-byte integer
		l means a signed, 4-byte long"""
		
		# entire filestring is 44 bytes long, with 12 variables (13 values)
		filetuple = struct.unpack('<2s 3H l I l 6I',filestring)
		header_dict = {}
		# assign dictionary key/value pairs and class attributes exactly
		# as laid out in cine640.pdf
		header_dict["Type"] = filetuple[0]
		header_dict["Headersize"] = filetuple[1]
		header_dict["Compression"] = filetuple[2]
		header_dict["Version"] = filetuple[3]
		header_dict["FirstMovieImage"] = filetuple[4]
		header_dict["TotalImageCount"] = filetuple[5]
		header_dict["FirstImageNo"] = filetuple[6]
		header_dict["ImageCount"] = filetuple[7]
		header_dict["OffImageHeader"] = filetuple[8]
		header_dict["OffSetup"] = filetuple[9]
		header_dict["OffImageOffsets"] = filetuple[10]
		header_dict["TriggerTime"] = (filetuple[11],filetuple[12])
		return header_dict

	def _get_BitmapInfoHeader(self,filestring):
		"""Takes output from cinefile.read(), parses it using struct.unpack()
		according to 
		<www.visionresearch.com/devzonedownloads/cine640.pdf>,
		and returns a dictionary of values for the BitmapInfoHeader structure.
		
		Parse first 44 bytes via hardcoded content order and size:
		This process produces, for example:
		In [88]: struct.unpack('<2sHHHl',cinefile.read(12))
		Out[88]: ('CI', 44, 0, 1, -348756)
		Where the tuple entries correspond to the fields 
		(as defined at www.visionresearch.com/devzonedownloads/cine640.pdf):
		(Type, Headersize, Compression, Version, FirstMovieImage)
		
		The format comes from the struct python module and reads as follows:
		< means little endian
		2s means a two-character string
		H means an unsigned, 2-byte integer
		l means a signed, 4-byte long
		
		"""
		
		# entire filestring is 40 bytes long, with 11 variables
		filetuple = struct.unpack('<I 2l 2H 2I 2l 2I',filestring)
		bitmap_dict = {}
		# assign dictionary key/value pairs and class attributes exactly
		# as laid out in cine640.pdf
		bitmap_dict["biSize"] = filetuple[0]
		bitmap_dict["biWidth"] = filetuple[1]
		bitmap_dict["biHeight"] = filetuple[2]
		bitmap_dict["biPlanes"] = filetuple[3]
		bitmap_dict["biBitCount"] = filetuple[4] 
		# note that this may be different from Setup.RealBPP
		# Pixels are stored only at 8 bits or 16 bits
		#     even if they are recorded at different depth
		bitmap_dict["biCompression"] = filetuple[5]
		bitmap_dict["biSizeImage"] = filetuple[6]
		bitmap_dict["biXPelsPerMeter"] = filetuple[7]
		bitmap_dict["biYPelsPerMeter"] = filetuple[8]
		bitmap_dict["biClrUsed"] = filetuple[9]
		bitmap_dict["biClrImportant"] = filetuple[10]
		return bitmap_dict
		
	def _get_Setup(self,filestring):
		"""Parse bytes 224-7148 via hardcoded content order and size.
		
		The first 136 bytes after the length (88-224) are skipped above 
		because they are all deprecated and don't display the correct data.
		
		Inside the rest of the structure, arrays of strings
		are parsed into single strings.  This is for my convenience, 
		since we don't ever use those fields.  These unparsed 
		strings are omitted from the class attributes.
		
		Additionally, blocks of deprecated fields, 
		fields involving the Signal Acquisition Module (SAM), or fields 
		that appear to be used solely by the PCC application for viewing
		are also omitted from the class attributes but can easily be added
		to the module.
		"""
		
		# entire filestring is 6904 bytes long, with many variables
		# the last 4096 bytes are the Description field.  
		# Example:
		# format codes in brackets indicate omitted/deprecated attributes
		# self.filetuple = struct.unpack('<2H [H] I l [B] I  ???? ???? [I] I 
		#     [2I] I [I] ???? 3I [l I 3l 3I 4I] 8f l 2f I',filestring) 
		
		# BOOL values are marked by ???? because for some reason, 
		#     cine BOOLs are 4 bytes
		# RECT values are actually four UINT values in a row 
		# WBGAIN types are actually two FLOAT values in a row 
		format_ImWidth_RealBPP_inclusive ="2H H I l B I ???? ????  I I 2I I I"\
		    + "???? 3I l I 3l 3I 4I 8f l 2f I" 
		# the next chunk is skipped stuff
		format_Conv8min_MCPercent_inclusive = "2I 30l 3I 4? 2I 16l 32I l 64f" 
		format_CICalib_Description_end_inclusive = "7I 8I 4I 4I 4096s"
		format_string = "<" + format_ImWidth_RealBPP_inclusive \
		    + format_Conv8min_MCPercent_inclusive \
		    + format_CICalib_Description_end_inclusive
		filetuple = struct.unpack(format_string,filestring)
		setup_dict = {}
		# setup_dict["filetuple"]=filetuple  #Could include entire tuple
		
		# assign dictionary key/value pairs and class attributes exactly
		# as laid out in cine640.pdf
		setup_dict["ImWidth"] = filetuple[0]
		setup_dict["ImHeight"] = filetuple[1]
		# skip filetuple[2] = EDRShutter16
		setup_dict["Serial"] = filetuple[3]
		# skip filetuple[4:15] = saturation, autoexposure, and PCC setup vars
		setup_dict["FrameRate"] = filetuple[16]
		# skip [17:18] - deprecated shutter vars
		setup_dict["PostTrigger"] = filetuple[19]
		# skip [20:24], deprecated and color vars
		setup_dict["CameraVersion"] = filetuple[25]
		setup_dict["FirmwareVersion"] = filetuple[26]
		setup_dict["SoftwareVersion"] = filetuple[27]
		# skip [28:50] - timezone and PCC setup vars 
		setup_dict["RealBPP"] = filetuple[51]
		# note that this may be different from BitmapInfoHeader.biBitCount.
		# Pixels are stored only at 8 bits or 16 bits
		#     even if they are recorded at different depth
		
		# skip [52:205] - PCC image processing, 
		#     8-bit memory conversion (N/A for 12 bit recordings),
		setup_dict["CICalib"] = filetuple[206]
		setup_dict["CalibWidth"] = filetuple[207]
		setup_dict["CalibHeight"] = filetuple[208]
		setup_dict["CalibRate"] = filetuple[209]
		setup_dict["CalibExp"] = filetuple[210]
		setup_dict["CalibEDR"] = filetuple[211]
		setup_dict["CalibTemp"] = filetuple[212]
		# skip [213:220] - unused options        
		setup_dict["Sensor"] = filetuple[221]
		setup_dict["ShutterNs"] = filetuple[222]
		setup_dict["EDRShutterNs"] = filetuple[223]
		setup_dict["FrameDelayNs"] = filetuple[224]
		# skip [225:228] - sidestamped image offsets
		# strip trailing zeros from description and encode
		desc_string = filetuple[229].rstrip('\x00')
		return setup_dict

	
	def _get_TaggedBlocks(self,cinefile,tag_start,framelims):		
	    # store tagged blocks as a dictionary since we don't 
	    # know how many blocks or how big they are
		blocks_dict = {}
		
		# Construct dictionary of cine block types with their names as values
		# Old block types (1000,1001) are omitted
		# NOTE: RangeData is included here, but it's not yet defined as of 
		#     cine640.pdf
		tag_type_dict = {1002:'TimeOnly',1003:'ExposureOnly',1004:'RangeData',\
			                 1005:'BinSig',1006:'AnaSig'}
		
		# Construct dictionary of block types with how many bytes each 
		#     data value takes
		# USAGE NOT YET IMPLEMENTED
		tag_data_size_dict = {1002:'8',1003:'4',1004:'1',\
			                      1005:'1',1006:'2'}
		tagged_length = 0
		# Keep list of tag header information for each block
		tag_headers = []  # for debugging
		# Move to beginning of tagged block section
		cinefile.seek(tag_start)
	    # Read in any tagged blocks until reaching the image data
		while tagged_length + tag_start <= \
			    self.CineFileHeader["OffImageOffsets"]-1:  
			# header is always 8 bytes     
			tag_header = struct.unpack("< I H H",cinefile.read(8))  
			tag_headers.append(tag_header)
			BlockSize = tag_header[0]  #size is first DWORD
			data_length = BlockSize - 8  #again, header is always 8 bytes
			BlockType = tag_header[1]  #type is first WORD
			# "Reserved" is second WORD; is 0 in last block, 1 otherwise
			blocks_left = tag_header[2] 

		    # make sure BlockType exists
			assert BlockType in tag_type_dict, "Unknown tagged block type: "\
			    + str(BlockType)
		    # read in data
			
			# WANT TO GENERALIZE SO THAT ALL THAT NEEDS TO BE SPECIFIED 
			# ARE THE APPROPRIATE VALUES IN THE BLOCK DICTIONARIES
			#    blocks_dict[tag_type_dict[BlockType]] = struct.unpack\
			    #     ("<"+block_format,cinefile.read(data_length))

			# FOR NOW, JUST USE IF/ELSE.  ONLY TWO BLOCK TYPES USED NORMALLY
			if BlockType == 1002:
				# Time only block, format = (seconds,fraction * 2**32)
				bytes_per_value = 8  #(32.32 bits)
				ntimes = data_length/bytes_per_value
				# full precision tuple of arrays
				TimeOnly = (numpy.ndarray(ntimes,int),\
					            numpy.ndarray(ntimes,int))  
				# lower precision floating point representation
				time_float = numpy.ndarray((ntimes),numpy.float) 
				
				for time_step in range(ntimes):
					# Read in Fraction field of Time64 structure
					fraction = struct.unpack("<I",cinefile.read(4))[0]
					# Read in Seconds field
					seconds = struct.unpack("<I",cinefile.read(4))[0]
					# Populate tuple
					TimeOnly[0][time_step] = fraction
					TimeOnly[1][time_step] = seconds

					# Populate array with time relative to trigger
					# Use 128-bit float to preserve precision during calc. 
					time_float[time_step] = numpy.float128(seconds \
					        - self.CineFileHeader["TriggerTime"][1])\
					        + numpy.float128(fraction \
					        - self.CineFileHeader["TriggerTime"][0])/(2**32)
				# Full representation
				blocks_dict["TimeOnly"] = zip(numpy.asarray(TimeOnly)[0,framelims[0]:framelims[1]],
							      numpy.asarray(TimeOnly)[1,framelims[0]:framelims[1]])
				# Convenience floating point representation
				blocks_dict["time_float"] = time_float[framelims[0]:framelims[1]]
			
			if BlockType == 1003:
				# Exposure only block, format = fraction * 2**32)
				bytes_per_value = 4  #(0.32 bits)
				nexp = data_length/bytes_per_value
				# full precision integer array (32/64 bits depending on arch)
				ExposureOnly = numpy.ndarray(nexp, int) 
				# (possibly) lower precision floating point representation
				exposure_float = numpy.ndarray(nexp,numpy.float) 
				
				for time_step in range(nexp):
					# Read in exposure fraction integer
					fraction = struct.unpack("<I",cinefile.read(4))[0]
					# Populate integer array
					ExposureOnly[time_step] = fraction
					# Populate float array
					# Use 128-byte float to preserve precision during calc. 
					exposure_float[time_step] = numpy.float(fraction) \
					    / numpy.float(2**32)
				# Full representation
				blocks_dict["ExposureOnly"] = ExposureOnly[framelims[0]:framelims[1]]
				# Convenience floating point representation
				blocks_dict["exposure_float"] = exposure_float[framelims[0]:framelims[1]]
			
			# add size of current block to total length of tagged portion
			tagged_length += BlockSize

		# add list of tag headers to dictionary (for debugging)
		#blocks_dict["tag_headers"] = tag_headers

		return blocks_dict # outside while loop


	def _get_Images(self,cinefile,start_pos,framelims):
		"""Reads image block into 3D numpy array.

		Note that pixel data is cast from UINT to FLOAT so that
		algebraic operations can be performed on the array.
		"""

		nx = self.Setup["ImWidth"]
		ny = self.Setup["ImHeight"]
		nframes = self.CineFileHeader["ImageCount"]
		pointer_array = numpy.ndarray((nframes),numpy.int64)

		# Read image pointer array (Q = unsigned int64)
		cinefile.seek(start_pos)  # make sure we are at image start position
		pointer_array = struct.unpack("<"+str(nframes)+"Q",
		                              cinefile.read(nframes*8))
		
		if framelims == None:
			framelims = (0,nframes)
		
		# Redefine nframes to actual number of frames to record
		nframes = framelims[1] - framelims[0]
		image_array = numpy.ndarray((nx,ny,nframes),float)
		# Go to first desired frame
		cinefile.seek(pointer_array[framelims[0]])

		# Read each image, skipping the annotations 
		for frame in range(nframes):
			if (frame !=0 and numpy.mod(frame,500) == 0):
				print "Read " + str(frame) + " frames."
			AnnotationSize = struct.unpack('<I',cinefile.read(4))[0]
			# Size of AnnotationSize is 4, and  pixel array size takes up 
			#     last 4 bytes of Annotation (first 4 already read)
			string_size = AnnotationSize - 8
			Annotation, ImageSize = struct.unpack("<"+str(string_size)+"s I",
				                              cinefile.read(AnnotationSize-4))

			if self.BitmapInfoHeader["biBitCount"] == 8:
				image_bits = struct.unpack("<"+str(ImageSize)+"B",   
                                                                  cinefile.read(ImageSize)) 
			else:
				image_bits = struct.unpack("<"+str(ImageSize/2)+"H",
				                                  cinefile.read(ImageSize))
			image_array[...,frame] = numpy.reshape(image_bits,(nx,ny))

		print "Read " + str(nframes) + " frames."
		return image_array
