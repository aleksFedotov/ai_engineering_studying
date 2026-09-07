import numpy as np

a = np.array([1.0,2.0,3.0])
b = np.array([3.0,-2.0,1.0])


dot = np.dot(a,b)
norm_a = np.linalg.norm(a)
norm_b = np.linalg.norm(b)
cos_sim = dot/(norm_a*norm_b)
print(cos_sim)