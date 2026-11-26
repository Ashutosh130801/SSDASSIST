import React from 'react';
import mark from '../assets/logo-mark.png';
import shade from '../assets/logo-shade.png';

/** Company logo, cut out of its black disc and tinted with the active palette.
 *  Layer 1: the mark's silhouette filled with the theme gradient. Layer 2: the original metallic
 *  shading (greyscale) blended on top so the bevels and highlights survive in any colour. */
export default function BrandMark({ size = 36, className = '', title = 'Logo' }) {
  return (
    <span className={'brand-mark ' + className} role="img" aria-label={title}
      style={{ width: size, height: size, '--mark': `url(${mark})` }}>
      <span className="bm-fill" />
      <img className="bm-shade" src={shade} alt="" draggable="false" />
    </span>
  );
}
