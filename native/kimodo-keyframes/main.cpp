// SPDX-License-Identifier: Apache-2.0
// Local Character adapter. Uses the pinned port's real conditioned DDIM path.
#include "ggml_weights.hpp"
#include "llm_text_encoder.hpp"
#include "denoiser.hpp"
#include "motion_decode.hpp"
#include "skeleton.hpp"
#include <algorithm>
#include <cmath>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <iterator>
#include <random>
#include <stdexcept>
#include <vector>

namespace {
std::vector<float> read_f32(const std::filesystem::path &path,size_t count) {
    if(std::filesystem::file_size(path)!=count*sizeof(float))throw std::runtime_error("Invalid keyframe array size");
    std::vector<float> out(count);std::ifstream file(path,std::ios::binary);
    if(!file.read(reinterpret_cast<char*>(out.data()),static_cast<std::streamsize>(count*sizeof(float))))throw std::runtime_error("Cannot read keyframe array");
    for(float v:out)if(!std::isfinite(v))throw std::runtime_error("Nonfinite keyframe value");
    return out;
}
void write_f32(const std::filesystem::path &path,const std::vector<float> &value) {
    std::ofstream file(path,std::ios::binary|std::ios::trunc);
    file.write(reinterpret_cast<const char*>(value.data()),static_cast<std::streamsize>(value.size()*sizeof(float)));
    if(!file)throw std::runtime_error("Cannot write generated motion");
}
}
int main(int argc,char**argv)try {
    if(argc!=11){std::cerr<<"usage: kmd-keyframes MOTION TEXT PROMPT FRAMES STEPS SEED OBSERVED MASK HEADING OUTPUT\n";return 2;}
    const auto frames=std::stoul(argv[4]),steps=std::stoul(argv[5]);
    if(frames<15||frames>900||steps<10||steps>200)throw std::runtime_error("Invalid keyframed generation length or steps");
    const auto seed=std::stoull(argv[6]);const float heading=std::stof(argv[9]);
    if(seed>=2147483648ULL||!std::isfinite(heading))throw std::runtime_error("Invalid seed or heading");
    const auto&s=kimodo::detail::soma30_spec;const auto dim=s.motion_dim();
    auto observed=read_f32(argv[7],frames*dim),mask=read_f32(argv[8],frames*dim);
    size_t constrained=0;for(float v:mask){if(v!=0.F&&v!=1.F)throw std::runtime_error("Keyframe mask must be binary");constrained+=v==1.F;}
    if(!constrained)throw std::runtime_error("At least one pose constraint is required");
    std::ifstream prompt_file(argv[3]);const std::string prompt{std::istreambuf_iterator<char>(prompt_file),{}};
    if(prompt.empty()||prompt.size()>4096)throw std::runtime_error("Invalid prompt");
    // Text first preserves the native port's Vulkan initialization order.
    auto encoder=kimodo::detail::llm_text_encoder::load(argv[2]);if(!encoder)throw std::runtime_error(encoder.error());
    auto embedding=(*encoder)->encode(prompt);if(!embedding)throw std::runtime_error(embedding.error());
    auto weights=kimodo::detail::ggml_motion_weights::load(argv[1]);if(!weights)throw std::runtime_error(weights.error());
    if((*weights)->skeleton_key()!=s.key||(*weights)->motion_dim()!=dim)throw std::runtime_error("Keyframes require SOMA30");
    auto gm=(*weights)->f32_values("stats.global_root.mean"),gs=(*weights)->f32_values("stats.global_root.std");
    auto bm=(*weights)->f32_values("stats.body.mean"),bs=(*weights)->f32_values("stats.body.std");
    if(!gm||!gs||!bm||!bs||gm->size()!=5||gs->size()!=5||bm->size()!=dim-5||bs->size()!=dim-5)throw std::runtime_error("Invalid normalization statistics");
    for(size_t t=0;t<frames;++t)for(size_t d=0;d<dim;++d){const float mean=d<5?(*gm)[d]:(*bm)[d-5],sd=d<5?(*gs)[d]:(*bs)[d-5];observed[t*dim+d]=(observed[t*dim+d]-mean)/std::sqrt(sd*sd+1.e-5F);}
    std::mt19937_64 rng(seed);std::normal_distribution<float> normal(0.F,1.F);std::vector<float> noise(frames*dim);
    for(float&v:noise)v=normal(rng);
    auto sampled=kimodo::detail::sample_motion_from_noise_conditioned(**weights,noise,*embedding,observed,mask,heading,frames,static_cast<unsigned>(steps),2.F,2.F);
    if(!sampled)throw std::runtime_error(sampled.error());
    auto decoded=kimodo::detail::decode_motion(*sampled,frames,s,*gm,*gs,*bm,*bs);if(!decoded)throw std::runtime_error(decoded.error());
    const std::filesystem::path output(argv[10]);std::filesystem::create_directories(output);
    write_f32(output/"root_positions.f32",decoded->root_positions);write_f32(output/"local_rotations_xyzw.f32",decoded->local_xyzw);
    std::cout<<"LOCAL_CHARACTER_KEYFRAMES_GENERATED "<<frames<<" constrained_features="<<constrained<<"\n";return 0;
}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}
