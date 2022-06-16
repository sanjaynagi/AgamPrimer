


def prepare_gDNA_sequence(target_loc, amplicon_size_range, genome_seq):
  """
  Extracts sequence of interest from genome sequence
  """
  # Set up range for the input sequence, we'll take the middle range of the amplicon size and add that either
  # side of the target SNP
  start = target_loc - np.mean(amplicon_size_range)
  end = target_loc + np.mean(amplicon_size_range)  
  # join array into be one character string, and store the positions of these sequences for later
  target_sequence = ''.join(genome_seq[start:end].compute().astype(str))
  gdna_pos = np.arange(start, end).astype(int) + 1
  print(f"The target sequence is {len(target_sequence)} bases long")

  # We need the target snp indices within the region of interest
  target_loc_primer3 = int(np.where(gdna_pos == target_loc)[0])
  target_loc_primer3 = [target_loc_primer3, 10]
  print(f"the target snp is {target_loc_primer3[0]} bp into our target sequence")
  return(target_sequence, target_loc_primer3, gdna_pos)

def prepare_cDNA_sequence(transcript, genome_seq):
  """
  Extract exonic sequence for our transcript and record exon-exon junctions
  """
  #subset gff to your gene
  gff = ag3.geneset()
  gff = gff.query(f"type == 'exon' & Parent == @transcript") 
  # Get fasta sequence for each of our exons, and remember gDNA position
  seq = dict()
  gdna_pos = dict()
  for i, exon in enumerate(zip(gff.start, gff.end)):
      seq[i] = ''.join(np.array(genome_seq)[exon[0]-1:exon[1]].astype(str))
      gdna_pos[i] = np.arange(exon[0]-1, exon[1])
  #concatenate exon FASTAs into one big sequence
  gdna_pos = np.concatenate(list(gdna_pos.values()))
  target_mRNA_seq = ''.join(seq.values())

  # Get list of exon junction positions
  exon_junctions = np.array(np.cumsum(gff.end - gff.start))[:-1]
  exon_sizes = np.array(gff.end - gff.start)[:-1]
  exon_junctions_pos = [ex + gff.iloc[i, 3] for i, ex in enumerate(exon_sizes)]
  print(f"Exon junctions for {transcript}:" ,exon_junctions, exon_junctions_pos, "\n")
  return(target_mRNA_seq, list(map(int, exon_junctions)), gdna_pos)


def rev_complement(seq):
    BASES ='NRWSMBDACGTHVKSWY'
    return ''.join([BASES[-j] for j in [BASES.find(i) for i in seq][::-1]])

def consecutive(data, stepsize=1):
    arr = np.split(data, np.where(np.diff(data) != stepsize)[0]+1)
    arr = [[a.min(), a.max()] for a in arr]
    return (arr)

def get_primer_alt_frequencies(primer_df, gdna_pos, pair, sample_set, assay='gDNA'):
  """
  Find the genomic locations of pairs of primers, and runs span_to_freq
  to get allele frequencies at those locations
  """
  primer_loc_fwd = primer_df.loc['PRIMER_LEFT', str(pair)][0]
  primer_size_fwd = primer_df.loc['PRIMER_LEFT', str(pair)][1]
  primer_loc_rev = primer_df.loc['PRIMER_RIGHT', str(pair)][0]+1
  primer_size_rev = primer_df.loc['PRIMER_RIGHT', str(pair)][1]
  
  freq_arr, ref_arr, pos_arr = get_primer_arrays(gdna_pos=gdna_pos, assaytype=assay)

  freq_fwd = freq_arr[primer_loc_fwd:primer_loc_fwd+primer_size_fwd]
  freq_rev = np.flip(freq_arr[primer_loc_rev-primer_size_rev:primer_loc_rev])
  ref_fwd = ref_arr[primer_loc_fwd:primer_loc_fwd+primer_size_fwd]
  ref_rev = ref_arr[primer_loc_rev-primer_size_rev:primer_loc_rev]
  ref_rev = np.array(list(rev_complement(''.join(ref_rev))), dtype=str)
  pos_fwd = pos_arr[primer_loc_fwd:primer_loc_fwd+primer_size_fwd]
  pos_rev = np.flip(pos_arr[primer_loc_rev-primer_size_rev:primer_loc_rev])

  fwd_df = pd.DataFrame({'position': pos_fwd, 'base':ref_fwd, 'alt_frequency':freq_fwd}) # Make dataframe for plotting
  rev_df = pd.DataFrame({'position': pos_rev, 'base':ref_rev, 'alt_frequency':freq_rev}) # Make dataframe for plotting
  fwd_df['base_pos'] = fwd_df['base'] + "_" + fwd_df['position'].astype(str)
  assert fwd_df.shape[0] == primer_size_fwd, "Wrong size primers"
  rev_df['base_pos'] = rev_df['base'] + "_" + rev_df['position'].astype(str) 
  assert rev_df.shape[0] == primer_size_rev, "Wrong size primers"
  return(fwd_df, rev_df)

def get_primer_arrays(gdna_pos, assaytype):

  if assaytype == 'gDNA':
    span_str=f'{contig}:{gdna_pos.min()}-{gdna_pos.max()}'                        
    ref_arr = ag3.genome_sequence(region=span_str).compute().astype(str)     # get dna sequence for span
    geno = ag3.snp_genotypes(region=span_str, sample_sets=sample_set).compute() # get genotypes
    freqs = allel.GenotypeArray(geno).count_alleles().to_frequencies()                                # calculate allele frequencies
    freq_arr = freqs[:, 1:].sum(axis=1)
    pos_arr = gdna_pos
  elif assaytype == 'qPCR':
    freq_arr = np.array([])
    ref_arr = np.array([])
    pos_arr = np.array([])
    exon_spans = np.array(consecutive(gdna_pos)) +1
    for span in exon_spans:
      span_str=f'{contig}:{span[0]}-{span[1]}'                        
      primer_ref_seq = ag3.genome_sequence(region=span_str).compute().astype(str)     # get dna sequence for span
      geno = ag3.snp_genotypes(region=span_str, sample_sets=sample_set).compute() # get genotypes
      freqs = allel.GenotypeArray(geno).count_alleles().to_frequencies()                                # calculate allele frequencies
      freq_arr = np.append(freq_arr, freqs[:, 1:].sum(axis=1))
      ref_arr = np.append(ref_arr, primer_ref_seq)
      pos_arr = np.append(pos_arr, np.arange(span[0], span[1]+1).astype(int))

  return(freq_arr, ref_arr, pos_arr)

def plot_pair_text(pair, ax, side, dict_dfs):
  """
  Plot text relating to primer characteristics (Tm etc)
  """
  tm = np.round(primer_df.loc[f'PRIMER_{side}_TM', str(pair)], 2)       
  gc = np.round(primer_df.loc[f'PRIMER_{side}_GC_PERCENT', str(pair)], 2)
  span = f"{int(dict_dfs[pair]['position'].min())}-{int(dict_dfs[pair]['position'].max())}"
  # Write text to plot for Tm, GC, span, and 3/5'
  ax.text(x=2, y=0.5, s=f"TM={tm}", bbox=dict(facecolor='white', edgecolor='black', alpha=0.4, boxstyle='round', pad=0.5))
  ax.text(x=2, y=0.7, s=f"GC={gc}", bbox=dict(facecolor='white', edgecolor='black', alpha=0.4, boxstyle='round', pad=0.5))
  ax.text(x=2, y=0.9, s=span, bbox=dict(facecolor='white', edgecolor='black', alpha=0.4, boxstyle='round', pad=0.5))
  ax.text(x=0.5, y=0.9, s="5'")
  ax.text(x=18, y=0.9, s="3'")

def plot_primer(primer_df, ax, i, dict_dfs, assay, side='LEFT'):
  """
  Plot primer allele frequencies and text
  """
  sns.scatterplot(ax=ax, x=dict_dfs[i]['base_pos'], y=dict_dfs[i]['alt_frequency'], s=200) 
  ax.set_xticklabels(dict_dfs[i]['base'])
  ax.set_ylim(0,1)
  ax.set_xlabel("")
  ax.set_ylabel("Alternate allele frequency")
  if side == 'RIGHT': 
    ax.set_ylabel("")
    ax.set_yticklabels("")

  if assay == 'qPCR':
    a = primer_df.loc[f'PRIMER_{side}', str(i)]
    a = a[0] - a[1] if side == 'RIGHT' else a[0] + a[1]
    arr = np.array(exon_junctions)- a
    if (np.abs(arr) < 18).any():
      bases_in_new_exon  = arr[np.abs(arr) < 18]
      plt.setp(ax.get_xticklabels()[bases_in_new_exon[0]:], backgroundcolor="antiquewhite") if side == 'RIGHT' else plt.setp(ax.get_xticklabels()[:bases_in_new_exon[0]], backgroundcolor="antiquewhite")

  ax.set_title(f"FWD primer {i}") if side == 'LEFT' else  ax.set_title(f"REV primer {i}") 
  plot_pair_text(i, ax, side, dict_dfs)

def plot_primer_pairs(primer_df, sample_set, n_primer_pairs, assay, save=True):
  """
  Loop through n primer pairs, retrieving frequency data and plot allele frequencies
  """
  di_fwd = {}
  di_rev = {}
  # Loop through each primer pair and get the frequencies of alternate alleles, storing in dict
  for i in range(n_primer_pairs):
    di_fwd[i], di_rev[i] = get_primer_alt_frequencies(primer_df, gdna_pos, i, sample_set, assay)
  # Plot data
  fig, ax = plt.subplots(n_primer_pairs , 2, figsize=[14, (n_primer_pairs*2)+2], constrained_layout=True)    
  fig.suptitle(f"{name} primer pairs | {sample_set} | target {target_loc} bp", fontweight='bold')
  for i in range(n_primer_pairs):
    plot_primer(primer_df, ax[i,0], i, di_fwd, assay, side='LEFT')
    plot_primer(primer_df, ax[i,1], i, di_rev, assay, side='RIGHT')
  if save: fig.savefig(f"{name}.primers.png")
  return(di_fwd, di_rev)