""" Reaction Network Class
This class bulds the basic structure to generate random reaction networks.
It includes methods to:
1. Constuct RN based on number of distict species "n"
    1.(a). The RN is stored as a dictionary, where each complex is represented by a key.
            The first entry for each key is a bool that is used in the add_reaction function below
            to ensure randomness in adding reactions

2. Add reaction paths between complexes of network based on "pN"

3. Progressvely update the deficiency value of network's deficiency "def"


"""
import math
import random
import numpy as np
import time
import decimal
import matplotlib.pyplot as plt


class Network(object):

    def __init__(self, complex_set, last_added, n=2, reaction_dict={}):
        """
            Initializes network based on the number of different species. For n different species,
            the number of distinct complexes in network is (n^2+3n+2)/2 := N
        """
        # first time constructor is called in build_RN
        if len(complex_set) == 0:
            self.__complex_set = set()
            self.__complex_set.add(last_added[0])
            self.__complex_set.add(last_added[1])

        else:
            temp = complex_set
            temp.add(last_added[0])
            temp.add(last_added[1])
            self.__complex_set = temp

        # maximum number of different species in RN
        self.__n = n

        self.__net_dict = reaction_dict

        self.__N = len(self.__complex_set)

        # array of species currently in network. 1 if in RN 0 else
        # self.__current_species = [0]*(self.__n + 1)

        # for complex in self.__complex_set:
        # self.update_curr_species(complex)

        # self.__num_distinct_species = sum(self.__current_species)

    def print_nodes(self):
        print(self.__net_dict)

    def get_nodes(self):
        return self.__net_dict

    def num_distinct_species(self):
        return self.__n

    def num_distinct_complexes(self):
        return self.__N

    def get_complex_set(self):
        return self.__complex_set

    def connected_components_3(self, last_added, lin_3, labels):

        # labels is a dictionary with an encoding of wich linkage class each complx belongs to

        # first time function is called, RN has only 2 complexes
        if lin_3 == 0:
            labels[last_added[0]] = 1
            labels[last_added[1]] = 1
            return [lin_3 + 1, labels]

        complex_1 = last_added[0]
        complex_2 = last_added[1]
        bool_1 = True
        bool_2 = True

        try:
            l_class_1 = labels[complex_1]
        except KeyError:
            bool_1 = False

        try:
            l_class_2 = labels[complex_2]
        except KeyError:
            bool_2 = False

        if bool_1 and bool_2 and l_class_1 == l_class_2:
            return [lin_3, labels]

        # complex 1 is in RN, but 2 is not
        if bool_2 and not bool_1:
            # print('exit 1')
            labels[complex_1] = l_class_2
            return [lin_3, labels]

        # complex 1 is in RN, but 2 is not
        if bool_1 and not bool_2:
            # print('exit 2')
            labels[complex_2] = l_class_1
            return [lin_3, labels]

        # neither complex is in RN
        elif (not bool_1) and (not bool_2):
            # print('exit 3')
            labels[complex_1] = lin_3 + 1
            labels[complex_2] = lin_3 + 1
            return [lin_3 + 1, labels]

        # both complexes are in RN
        elif bool_1 and bool_2:
            # print('exit 4')

            min_linkage = min(l_class_1, l_class_2)
            max_linkage = max(l_class_1, l_class_2)

            for complex in labels:

                if labels[complex] == max_linkage:
                    labels[complex] = min_linkage

                elif labels[complex] > max_linkage:
                    labels[complex] -= 1

            return [lin_3 - 1, labels]


    def bin_to_string(self, num_code):
        """ Converts the binary encoding into corresponding string of a given complex"""

        n = self.__n
        overall_N = (n ** 2 + 3 * n + 2) / 2

        # returns error if requested bin code exceeds total number of complexes
        if int(num_code) > overall_N:
            print('Binary code is too large for network')
            return None

        # returns '0' for the empty complex
        if int(num_code) == 0:
            return str({0})

        # deals with simple complexes
        elif int(num_code) <= n:
            return 'S_' + str(int(num_code))

        # deals with the cases '2S_i'
        elif int(num_code) > n and int(num_code) <= 2 * n:
            return '2S_' + str(int(num_code) - n)

        # deals with cases 'S_i+S_j'
        else:

            # iterates through first complexes
            cum_sum = 0
            for j in range(1, n):

                cum_sum += j - 1
                for i in range((j + 1) * n + 1 - cum_sum, (j + 2) * n - (cum_sum + j) + 1):
                    if num_code == i:
                        return 'S_' + str(j) + '+S_' + str(int(num_code) - ((j + 1) * n + 1 - cum_sum) + j + 1)


    def bin_to_vector_3(self, num_code):
        """ Converts the binary encoding into corresponding string of a given complex"""

        n = self.__n

        # length is n+1 to account for the 0 complex
        complex_vector = [0] * (n + 1)

        if num_code == 0:
            complex_vector[0] = 1

        # deals with simple complexes
        if num_code <= n:
            complex_vector[num_code] = 1

        # deals with the cases '2S_i'
        elif num_code > n and num_code <= 2 * n:
            complex_vector[num_code - n] = 2

        # deals with cases 'S_i+S_j'
        else:
            # iterates through first complexes
            cum_sum = 0
            for j in range(1, n):

                cum_sum += j - 1
                for i in range((j + 1) * n + 1 - cum_sum, (j + 2) * n - (cum_sum + j) + 1):
                    if num_code == i:
                        complex_vector[j] = 1
                        complex_vector[num_code - ((j + 1) * n + 1 - cum_sum) + j + 1] = 1

        return complex_vector


    def get_vector(self, react_vector, prod_vector):
        """ Computes the reaction vectors for given reaction in network. This function is applied to the clean network.
        """

        return [prod_vector[i] - react_vector[i] for i in range(len(prod_vector))]

    def build_RN(n, pN=0.5):
        """Build RN by adding a reaction between each pair of complexes based on value of pN. Methods works by
        visiting each pair of complexes exactly one time and adding a reaction based on the value of pN, with higher
        probability of adding reaction for higher value of pN"""

        if pN > 1 or pN <= 0:
            return [0, 0, False, 0]

        N = int((n ** 2 + 3 * n + 2) / 2)
        new_net_dic = {}
        clean_net = 0
        valid_RN = False
        mean_degree = 0
        # lin = 0
        lin_3 = 0
        complex_set = set()

        labels = {}

        added = [[False] * N] * N

        # exit loop after all pairs of complexes have been visited
        for i in range(N):
            for j in range(N):

                if i != j and added[i][j] == False:

                    # Add or not reaction based on pN
                    coin = random.uniform(0, 1)

                    # add reaction between complex i and complex j
                    if coin <= pN:

                        valid_RN = True
                        last_added = []
                        reaction_vectors = []
                        added[j][i] = True
                        try:
                            new_net_dic[i].append(j)
                            last_added.append([i, j])
                        except KeyError:
                            new_net_dic[i] = []
                            new_net_dic[i].append(j)
                            last_added.append([i, j])
                        try:
                            new_net_dic[j].append(i)
                            last_added.append([j, i])
                        except KeyError:
                            new_net_dic[j] = []
                            new_net_dic[j].append(i)
                            last_added.append([j, i])

                        last_added = last_added[0]

                        clean_net = Network(complex_set, last_added, n, new_net_dic)
                        complex_set = clean_net.get_complex_set()

                        [defi_3, lin_3, labels] = clean_net.build_RN_helper_3(last_added, lin_3, labels)

                        # [defi, lin] = clean_net.build_RN_helper()

                        if defi_3 > 0:
                            # print(times)
                            return [0, mean_degree, valid_RN, lin_3]

        if valid_RN:
            for complex in clean_net.__net_dict:
                mean_degree += len(clean_net.__net_dict[complex])
            mean_degree = mean_degree / clean_net.__N
        # print(times)
        return [clean_net, mean_degree, valid_RN, lin_3]

    def build_RN_helper_3(self, last_added, lin_3, labels):

        reaction_vectors = []
        added = [[False] * self.__N] * self.__N

        # counter variables
        a = 0
        b = 0

        for react in self.__net_dict:

            for prod in self.__net_dict[react]:

                if added[a][b] is False:
                    prod_vector = self.bin_to_vector_3(prod)
                    react_vector = self.bin_to_vector_3(react)
                    reaction_vectors.append(self.get_vector(react_vector, prod_vector))
                    added[b][a] = True
                    b += 1
            a += 1
            b = 0

        [defi, lin, labels] = self.deficiency_3(reaction_vectors, last_added, lin_3, labels)

        return [defi, lin, labels]


    def deficiency_3(self, reaction_vectors, last_added, lin_3, labels):
        # last_added is the last reaction added to RN

        # sub_dim = numpy.linalg.matrix_rank(numpy.matrix(reaction_vectors))

        s = np.linalg.svd(np.matrix(reaction_vectors), full_matrices=False, compute_uv=False)
        sub_dim_svd = 0
        for i in s:
            if decimal.Decimal(i) < decimal.Decimal('1.0e-15'):
                break
            sub_dim_svd += 1

        num_distinct_complexes = self.__N

        [num_linkage, labels] = self.connected_components_3(last_added, lin_3, labels)

        return [num_distinct_complexes - num_linkage - sub_dim_svd, num_linkage, labels]


    def visualize_RN(self):
        """Displays a matrix N1 by N1, where entry (i,j) is 1 if there's a reaction between i and j and 0 else.
        Where N1 is the number of complexes present in network (N1 <= N)"""

        react_dict = self.__net_dict
        N = len(react_dict)
        keys = list(react_dict.keys())

        # construct top of matrix
        matrix_RN = []
        matrix_RN.append(['---'])

        for i in range(N):
            current_complex = self.bin_to_string(keys[i])
            matrix_RN[0].append(current_complex)

        # construct remaining parts
        count = 0
        for i in range(N):
            row_leader = self.bin_to_string(keys[i])
            matrix_RN.append([row_leader])
            count += 1

            # if complex i reacts from/to complex j, entry is 1. Else entry is 0
            for j in keys:

                if j in react_dict[keys[i]]:
                    matrix_RN[count].append(['1'])
                else:
                    matrix_RN[count].append(['0'])

        print('\n'.join([''.join(['{:10}'.format(str(item)) for item in row]) for row in matrix_RN]))

        return

    def get_def_vec(n):

        N = (n ** 2 + 3 * n + 2) / 2
        thresh = (2 * (2 ** 1 / 2)) / (N ** 1.5)
        num_runs = 1000

        # Build range so as to have more data points around threshold
        temp = np.linspace(0.1 * thresh, 10 * thresh, 100)
        temp_start = np.linspace(0.00001 * thresh, 0.099 * thresh, 50)
        temp_end = np.linspace(10.1 * thresh, 1, 10)

        range_pN = np.append(temp_start, temp)
        range_pN = np.append(range_pN, temp_end)

        defi = [0] * len(range_pN)
        count = 0

        for pN in range_pN:

            print('------------------------------------------------------------', count)
            def_zero_count = 0
            def_non_zero_count = 0

            for i in range(num_runs):
                [final_net, mean_degree, valid_flag, lin_3] = Network.build_RN(n, pN)
                if final_net != 0 and valid_flag is True:
                    def_zero_count += 1
                    # print(mean_degree)

                if final_net == 0 and valid_flag is True:
                    def_non_zero_count += 1

            if (def_zero_count + def_non_zero_count) != 0:
                defi[count] = def_zero_count / (def_zero_count + def_non_zero_count)
            else:
                defi[count] = 0
            count += 1

        return [range_pN, defi]

[range_pN, defi] = Network.get_def_vec(12)
print(range_pN)
print(defi)