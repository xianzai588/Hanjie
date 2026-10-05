"""Planning times for dry normal-product inspection; no measured cycle log."""
import math

DRY_STEPS = dict(process_record_review=30,ten_region_endoscopy=200,
                 loose_item_count=30,clean_cover_and_seal=40)
CMM_STEPS = dict(independent_A_B_datums=90,five_continuous_rings=126,
                 four_axial_generatrices=60,probe_repositioning=24,fit_and_record=60)
PT_STEPS = dict(pan_install_seal_check=75,local_prepare=30,apply_penetrant=30,
                wipe_and_dry=60,apply_developer=30,read_and_record=90,
                local_clean_and_dry=90,controlled_handoff=75)
UT_STEPS = dict(calibration=60,scan=300,read_and_record=60,
                pan_drain_dry_and_withdraw=100,probe_change=50,handoff=30)
HONING_STEPS = dict(cup_and_upper_cover_install_interlock=75,selective_removal=35,
                    drain_dry_and_closed_withdrawal=70,process_record=20)


def evaluate(interval_s,requires_honing=True):
    dry=sum(DRY_STEPS.values());one_scan=sum(CMM_STEPS.values())
    repeats=2 if requires_honing else 1;cmm=one_scan*repeats
    pt=sum(PT_STEPS.values());ut=sum(UT_STEPS.values())
    honing=sum(HONING_STEPS.values()) if requires_honing else 0
    manual=pt+ut+cmm+dry+honing
    return dict(basis='design planning input; trial timing replaces these values before production',
        normal_product_flow='local isolated PT/UT; independent CMM; dry endoscopy/record review/sealing; no cavity wash',
        dry_cleanliness_steps_s=DRY_STEPS,cleanliness_inspection_elapsed_s=dry,
        cleanliness_inspection_operator_work_s=dry,cleanliness_parallel_positions=math.ceil(dry/interval_s),
        finishing_branch='limited_honing_required' if requires_honing else 'direct_size_no_honing',
        PT_steps_s=PT_STEPS,UT_steps_s=UT_STEPS,
        CMM_steps_per_scan_s=CMM_STEPS,CMM_scan_count=repeats,CMM_single_scan_time_s=one_scan,
        CMM_station_time_s=cmm,CMM_parallel_stations=math.ceil(cmm/interval_s),
        honing_steps_s=HONING_STEPS if requires_honing else {},honing_station_time_s=honing,
        honing_parallel_stations=math.ceil(honing/interval_s),
        NDT_total_operator_work_s=pt+ut+cmm,NDT_operator_equivalents=math.ceil((pt+ut+cmm)/interval_s),
        inspection_total_operator_work_s=manual,inspection_operator_equivalents=math.ceil(manual/interval_s),
        sacrificial_extraction_elapsed_s=1800,sacrificial_extraction_operator_work_s=480,
        sacrificial_test_frequency='first qualification, process change and designated lot sample; separate laboratory capacity, not each product')


if __name__=='__main__':
    import json
    print(json.dumps({str(t):{branch:evaluate(t,flag) for branch,flag in [('direct',False),('honing',True)]}
        for t in (462.54545454545,231.27272727273)},ensure_ascii=False,indent=2))
