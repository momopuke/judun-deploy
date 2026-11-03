import unittest
import SC_VPS_Rescue_v10 as v10

def safe(**changes):
    base=dict(seconds=15,memory_full_pct=8,io_full_pct=1,
       major_faults_per_s=40,high_events_per_s=70,
       ram_available_mib=620,swap_free_mib=470,oom_kill=0)
    base.update(changes)
    return base

class MemorySafety(unittest.TestCase):
    def four(self,**changes): return [safe(**changes) for _ in range(4)]
    def test_steady_conditions(self): self.assertTrue(v10.assess(self.four())[0])
    def test_partial_window(self): self.assertFalse(v10.assess(self.four()[:3])[0])
    def test_short_interval(self): self.assertFalse(v10.assess(self.four(seconds=5))[0])
    def test_memory_full(self): self.assertFalse(v10.assess(self.four(memory_full_pct=50))[0])
    def test_major_faults(self): self.assertFalse(v10.assess(self.four(major_faults_per_s=300))[0])
    def test_critical_major_fault(self):
        w=self.four();w[2]['major_faults_per_s']=500
        self.assertFalse(v10.assess(w)[0])
    def test_io_full(self): self.assertFalse(v10.assess(self.four(io_full_pct=30))[0])
    def test_low_available_memory(self): self.assertFalse(v10.assess(self.four(ram_available_mib=100))[0])
    def test_low_swap(self): self.assertFalse(v10.assess(self.four(swap_free_mib=20))[0])
    def test_oom_event(self): self.assertFalse(v10.assess(self.four(oom_kill=1))[0])
    def test_high_throttling(self): self.assertFalse(v10.assess(self.four(high_events_per_s=2000))[0])
    def test_missing_kernel_counter(self): self.assertFalse(v10.assess(self.four(memory_full_pct=None))[0])

if __name__ == '__main__': unittest.main()
