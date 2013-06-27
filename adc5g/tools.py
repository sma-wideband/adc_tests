from struct import pack, unpack
from opb import (
    OPB_CONTROLLER,
    OPB_DATA_FMT,
    inc_mmcm_phase,
    )
from spi import (
    get_spi_control,
    set_spi_control,
    )


def total_glitches(core, bitwidth=8):
    ramp_max = 2**bitwidth - 1
    glitches = 0
    for i in range(len(core)-1):
        diff = core[i+1] - core[i]
        if (diff!=1) and (diff!=-ramp_max):
            glitches += 1
    return glitches


def get_snapshot(roach, snap_name, bitwidth=8, man_trig=True, wait_period=2):
    """
    Reads a one-channel snapshot off the given 
    ROACH and returns the time-ordered samples.
    """

    grab = roach.snapshot_get(snap_name, man_trig=man_trig, wait_period=2)
    data = unpack('%ib' %grab['length'], grab['data'])

    return list(d for d in data)


def get_test_vector(roach, snap_names, bitwidth=8, man_trig=True, wait_period=2):
    """
    Sets the ADC to output a test ramp and reads off the ramp,
    one per core. This should allow a calibration of the MMCM
    phase parameter to reduce bit errors.

    core_a, core_c, core_b, core_d = get_test_vector(roach, snap_names)

    NOTE: This function requires the ADC to be in "test" mode, please use 
    set_spi_control(roach, zdok_n, test=1) before-hand to be in the correct 
    mode.
    """
    data_out = []
    cores_per_snap = 4/len(snap_names)
    for snap in snap_names:
        data = get_snapshot(roach, snap, bitwidth, man_trig=man_trig, wait_period=2)
        data_bin = list(((p+128)>>1) ^ (p+128) for p in data)
        for i in range(cores_per_snap):
            data_out.append(data_bin[i::cores_per_snap])
    return data_out


def calibrate_mmcm_phase(roach, zdok_n, snap_names, bitwidth=8, man_trig=True, wait_period=2):
    """
    This function steps through all 56 steps of the MMCM clk-to-out 
    phase and finds total number of glitchss in the test vector ramp 
    per core. It then finds the least glitchy phase step and sets it.
    """
    #orig_control = get_spi_control(roach, zdok_n)
    #set_spi_control(roach, zdok_n, test=1)
    glitches_per_ps = []
    for ps in range(56):
        core_a, core_c, core_b, core_d = get_test_vector(roach, snap_names, man_trig=man_trig, wait_period=2)
        glitches = total_glitches(core_a, 8) + total_glitches(core_c, 8) + \
            total_glitches(core_b, 8) + total_glitches(core_d, 8)
        glitches_per_ps.append(glitches)
        inc_mmcm_phase(roach, zdok_n)
    zero_glitches = [gl==0 for gl in glitches_per_ps]
    n_zero = 0
    longest_min = None
    while True:
        try:
            rising  = zero_glitches.index(True, n_zero)
            n_zero  = rising + 1
            falling = zero_glitches.index(False, n_zero)
            n_zero  = falling + 1
            min_len = falling - rising
            if min_len > longest_min:
                longest_min = min_len
                optimal_ps = rising + int((falling-rising)/2)
        except ValueError:
            break
    #set_spi_control(roach, zdok_n, **orig_control)
    if longest_min==None:
        #raise ValueError("No optimal MMCM phase found!")
        return None, glitches_per_ps
    else:
        for ps in range(optimal_ps):
            inc_mmcm_phase(roach, zdok_n)
        return optimal_ps, glitches_per_ps

