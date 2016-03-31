
import pyximport; pyximport.install()

import numpy as np
import numpy.linalg as la

from rlscore.utilities import array_tools
from rlscore.utilities import decomposition

from rlscore.utilities import sampled_kronecker_products

from rlscore.pairwise_predictor import LinearPairwisePredictor
from rlscore.pairwise_predictor import KernelPairwisePredictor

from rlscore.pairwise_predictor import PairwisePredictorInterface

class KronRLS(PairwisePredictorInterface):
    
    """Regularized least-squares regression with
    paired-input (dyadic) data and Kronecker kernels.
    Closed form solution for complete data set with labels for all pairs known.
    

    Parameters
    ----------
    X1 : {array-like}, shape = [n_samples1, n_features1] 
        Data matrix 1 (for linear KronRLS)
        
    X2 : {array-like}, shape = [n_samples2, n_features2] 
        Data matrix 2 (for linear KronRLS)
        
    K1 : {array-like}, shape = [n_samples1, n_samples1]
        Kernel matrix 1 (for kernel KronRLS)

    K2 : {array-like}, shape = [n_samples1, n_samples1]
        Kernel matrix 2 (for kernel KronRLS)
        
    Y : {array-like}, shape = [n_samples1*n_samples2]
        Training set labels. Label for (X1[i], X2[j]) maps to
        Y[i + j*n_samples1] (column order).
        
    regparam : float, optional
        regularization parameter, regparam > 0 (default=1.0)
        
    Attributes
    -----------
    predictor : {LinearPairwisePredictor, KernelPairwisePredictor}
        trained predictor
                  
    Notes
    -----
    
    Computational complexity of training:

    TODO
     
    KronRLS implements the closed form solution described in [1,2]. In the publications only special case
    X1 = X2 (or equivalently K1 = K2) is considered, while this implementation also allows the two sets
    of inputs to be from different domains. By default KronRLS trains a regression method that minimizes
    mean-squared error.
    
    Currently, Kronecker RankRLS that minimizes magnitude preserving ranking error
    can be trained with method solve_linear_conditional_ranking(...) (yes, this is a hack and no, kernels
    are currently not supported for ranking). Inputs from domain 1 act as queries, and inputs from domain
    2 as objects to be ranked.
    
    References
    ----------
    
    [1] Tapio Pahikkala, Willem Waegeman, Antti Airola, Tapio Salakoski, and Bernard De Baets. Conditional ranking on relational data.
    Machine Learning and Knowledge Discovery in Databases (ECML PKDD), 2010
    
    [2] Tapio Pahikkala, Antti Airola, Michiel Stock, Bernard De Baets, and Willem Waegeman.
    Efficient regularized least-squares algorithms for conditional ranking on relational data.
    Machine Learning, 93(2-3):321--356, 2013.
    """
    
    
    def __init__(self, **kwargs):
        Y = kwargs["Y"]
        Y = array_tools.as_2d_array(Y)
        Y = np.mat(Y)
        if kwargs.has_key('K1'):
            K1 = np.mat(kwargs['K1'])
            K2 = np.mat(kwargs['K2'])
            Y = Y.reshape((K1.shape[0], K2.shape[0]), order = 'F')
            self.K1, self.K2 = K1, K2
            self.kernelmode = True
        else:
            X1 = np.mat(kwargs['X1'])
            X2 = np.mat(kwargs['X2'])
            Y = Y.reshape((X1.shape[0], X2.shape[0]), order = 'F')
            self.X1, self.X2 = X1, X2
            self.kernelmode = False
        self.Y = Y
        if kwargs.has_key("regparam"):
            self.regparam = kwargs["regparam"]
        else:
            self.regparam = 1.
        self.trained = False
        self.solve(self.regparam)
    
    
    def solve(self, regparam):
        """Re-trains KronRLS for the given regparam
               
        Parameters
        ----------
        regparam : float, optional
            regularization parameter, regparam > 0
        """
        self.regparam = regparam
        if self.kernelmode:
            K1, K2 = self.K1, self.K2
            #assert self.Y.shape == (self.K1.shape[0], self.K2.shape[0]), 'Y.shape!=(K1.shape[0],K2.shape[0]). Y.shape=='+str(Y.shape)+', K1.shape=='+str(self.K1.shape)+', K2.shape=='+str(self.K2.shape)
            if not self.trained:
                self.trained = True
                evals1, V  = la.eigh(K1)
                evals1 = np.mat(evals1).T
                V = np.mat(V)
                self.evals1 = evals1
                self.V = V
                
                evals2, U = la.eigh(K2)
                evals2 = np.mat(evals2).T
                U = np.mat(U)
                self.evals2 = evals2
                self.U = U
                self.VTYU = V.T * self.Y * U
            
            newevals = 1. / (self.evals1 * self.evals2.T + regparam)
            
            self.A = np.multiply(self.VTYU, newevals)
            self.A = self.V * self.A * self.U.T
            self.A = np.asarray(self.A)
            label_row_inds, label_col_inds = np.unravel_index(np.arange(K1.shape[0] * K2.shape[0]), (K1.shape[0],  K2.shape[0]))
            label_row_inds = np.array(label_row_inds, dtype = np.int32)
            label_col_inds = np.array(label_col_inds, dtype = np.int32)
            self.predictor = KernelPairwisePredictor(self.A.ravel(), label_row_inds, label_col_inds)
        else:
            X1, X2 = self.X1, self.X2
            Y = self.Y.reshape((X1.shape[0], X2.shape[0]), order='F')
            if not self.trained:
                self.trained = True
                svals1, V, rsvecs1 = decomposition.decomposeDataMatrix(X1.T)
                self.svals1 = svals1.T
                self.evals1 = np.multiply(self.svals1, self.svals1)
                self.V = V
                self.rsvecs1 = np.mat(rsvecs1)
                
                if X1.shape == X2.shape and (X1 == X2).all():
                    svals2, U, rsvecs2 = svals1, V, rsvecs1
                else:
                    svals2, U, rsvecs2 = decomposition.decomposeDataMatrix(X2.T)
                self.svals2 = svals2.T
                self.evals2 = np.multiply(self.svals2, self.svals2)
                self.U = U
                self.rsvecs2 = np.mat(rsvecs2)
                
                self.VTYU = V.T * Y * U
            
            kronsvals = self.svals1 * self.svals2.T
            
            newevals = np.divide(kronsvals, np.multiply(kronsvals, kronsvals) + regparam)
            self.W = np.multiply(self.VTYU, newevals)
            self.W = self.rsvecs1.T * self.W * self.rsvecs2
            self.predictor = LinearPairwisePredictor(np.array(self.W))
    
    
    def solve_linear_conditional_ranking(self, regparam):
        """Trains conditional ranking KronRLS, that ranks objects from
        domain 2 against objects from domain 1.
               
        Parameters
        ----------
        regparam : float, optional
            regularization parameter, regparam > 0 (default=1.0)
            
        Notes
        -----
        Minimizes RankRLS type of loss. Currently only linear kernel
        supported. Including the code here is a hack, this should
        probably be implemented as an independent learner.
        """
        self.regparam = regparam
        X1, X2 = self.X1, self.X2
        Y = self.Y.reshape((X1.shape[0], X2.shape[0]), order = 'F')
        
        svals1, V, rsvecs1 = decomposition.decomposeDataMatrix(X1.T)
        self.svals1 = svals1.T
        self.evals1 = np.multiply(self.svals1, self.svals1)
        self.V = V
        self.rsvecs1 = np.mat(rsvecs1)
        
        qlen = X2.shape[0]
        onevec = (1. / np.math.sqrt(qlen)) * np.mat(np.ones((qlen, 1)))
        C = np.mat(np.eye(qlen)) - onevec * onevec.T
        
        svals2, U, rsvecs2 = decomposition.decomposeDataMatrix(X2.T * C)
        self.svals2 = svals2.T
        self.evals2 = np.multiply(self.svals2, self.svals2)
        self.U = U
        self.rsvecs2 = np.mat(rsvecs2)
        
        self.VTYU = V.T * Y * C * U
        
        kronsvals = self.svals1 * self.svals2.T
        
        newevals = np.divide(kronsvals, np.multiply(kronsvals, kronsvals) + regparam)
        self.W = np.multiply(self.VTYU, newevals)
        self.W = self.rsvecs1.T * self.W * self.rsvecs2
        self.predictor = LinearPairwisePredictor(np.array(self.W))
    
    
    def in_sample_loo(self):
        """
        Computes the in-sample leave-one-out cross-validation predictions. By in-sample we denote the
        setting, where we leave out one entry of Y at a time.
        
        Returns
        -------
        F : array, shape = [n_samples1*n_samples2]
            Training set labels. Label for (X1[i], X2[j]) maps to
            F[i + j*n_samples1] (column order).
        """
        if not self.kernelmode:
            X1, X2 = self.X1, self.X2
            P = X1 * self.W * X2.T
        else:
            P = self.K1 * self.A * self.K2.T
        
        newevals = np.multiply(self.evals2 * self.evals1.T, 1. / (self.evals2 * self.evals1.T + self.regparam))
        Vsqr = np.multiply(self.V, self.V)
        Usqr = np.multiply(self.U, self.U)
        #loopred = mat(zeros((self.V.shape[0], self.U.shape[0])))
        #print self.U.shape[0], self.V.shape[0], self.Y.shape, loopred.shape, P.shape
        #for i in range(self.V.shape[0]):
            #cache = Vsqr[i] * newevals.T
            #for j in range(self.U.shape[0]):
            #    ccc = (cache * Usqr[j].T)[0, 0]
            #    loopred[i, j] = (1. / (1. - ccc)) * (P[i, j] - ccc * self.Y[i, j])
            #    #loopred[i, j] = P[i, j]
        ccc = Vsqr * newevals.T * Usqr.T
        loopred = np.multiply(1. / (1. - ccc), P - np.multiply(ccc, self.Y))
        return np.asarray(loopred).ravel(order = 'F')
    
    
    def _compute_ho(self, row_inds, col_inds):
        if not self.kernelmode:
            X1, X2 = self.X1, self.X2
            P_ho = X1[row_inds] * self.W * X2.T[:, col_inds]
        else:
            P_ho = self.K1[row_inds] * self.A * self.K2.T[:, col_inds]
        
        newevals = np.multiply(self.evals2 * self.evals1.T, 1. / (self.evals2 * self.evals1.T + self.regparam))
        
        rowcount = len(row_inds)
        colcount = len(col_inds)
        hosize = rowcount * colcount
        
        VV = np.mat(np.zeros((rowcount * rowcount, self.V.shape[1])))
        UU = np.mat(np.zeros((colcount * colcount, self.U.shape[1])))
        
        def bar():
            for i in range(len(row_inds)):
                ith_row = self.V[row_inds[i]]
                for h in range(len(row_inds)):
                    VV[i * rowcount + h] = np.multiply(ith_row, self.V[row_inds[h]])
            
            for j in range(len(col_inds)):
                jth_col = self.U[col_inds[j]]
                for k in range(len(col_inds)):
                    UU[j * colcount + k] = np.multiply(jth_col, self.U[col_inds[k]])
        
        def baz():
            #print VV.shape, newevals.shape, UU.T.shape
            B_in_wrong_order = VV * newevals.T * UU.T
            
            #B_in_right_order = mat(zeros((hosize, hosize)))
            
            #for i in range(len(row_inds)):
            #    for j in range(len(col_inds)):
            #        for h in range(len(row_inds)):
            #            for k in range(len(col_inds)):
            #                B_in_right_order[i * colcount + j, h * colcount + k] = B_in_wrong_order[i * rowcount + h, j * colcount + k]
            
            #print B_in_right_order
            #print B_in_right_order.shape, B_in_wrong_order.shape, rowcount, colcount
            B_in_right_order = np.mat(np.zeros((hosize, hosize)))
            sampled_kronecker_products.cpy_reorder(B_in_right_order, B_in_wrong_order, rowcount, colcount)
            #print B_in_right_order
            #print
            hopred = la.inv(np.mat(np.eye(hosize)) - B_in_right_order) * (P_ho.ravel().T - B_in_right_order * self.Y[np.ix_(row_inds, col_inds)].ravel().T)
            return hopred
        bar()
        hopred = baz()
        #print rowcount, colcount, hosize, hopred.shape
        return np.asarray(hopred.reshape(rowcount, colcount))