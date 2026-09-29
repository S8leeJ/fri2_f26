mayankk@bender:~/fri2_f26/audio_signals_FRI_II$ python3 tools/check_speed.py 
/usr/lib/python3/dist-packages/scipy/__init__.py:146: UserWarning: A NumPy version >=1.17.3 and <1.25.0 is required for this version of SciPy (detected version 1.26.4
  warnings.warn(f"A NumPy version >={np_minversion} and <{np_maxversion}"

  budget is 128 ms per block, which is how often audio arrives.
  Anything close to that will overflow.

  loading the voice detector...
  loudness                  0.0 ms     0%  
  voice detection           0.3 ms     0%  
  writing to the stores     5.1 ms     4%  #

  total                     5.5 ms     4%

  Plenty of headroom. If overflow still appears, the audio thread is
  being starved by something else on the machine rather than by this code.
mayankk@bender:~/fri2_f26/audio_signals_FRI_II$ ^C