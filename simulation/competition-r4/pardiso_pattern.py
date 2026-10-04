"""Reuse symbolic analysis only; refactor every changed numerical matrix.

Intel oneMKL PARDISO phases 13/23. Thermal and mechanical systems must use
separate instances so their different graphs cannot overwrite each other.
"""
import numpy as np
from scipy.sparse import triu
import pypardiso


class SymmetricPatternSolver:
    def __init__(self):
        self.solver=pypardiso.PyPardisoSolver(mtype=2)
        self.pattern=None
        self.analysis_calls=0
        self.refactor_calls=0

    def __call__(self, matrix, rhs):
        difference=matrix-matrix.T
        if difference.nnz and np.max(abs(difference.data))>1e-10*max(abs(matrix.data).max(),1):
            raise RuntimeError('asymmetric tangent passed to symmetric solver')
        upper=triu(matrix,format='csr')
        self.solver._check_A(upper)
        vector=self.solver._check_b(upper,rhs)
        same=self.pattern is not None and self.pattern[0]==upper.shape and np.array_equal(self.pattern[1],upper.indptr) and np.array_equal(self.pattern[2],upper.indices)
        if same:
            self.solver.set_phase(23)
            self.refactor_calls+=1
        else:
            if self.pattern is not None:self.solver.free_memory(everything=True)
            self.solver.set_phase(13)
            self.pattern=(upper.shape,upper.indptr.copy(),upper.indices.copy())
            self.analysis_calls+=1
        answer=self.solver._call_pardiso(upper,vector)
        if np.linalg.norm(matrix@answer-rhs)>.001:
            raise RuntimeError('PARDISO linear residual exceeds 0.001')
        return answer
